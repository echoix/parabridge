#!/usr/bin/env python

# parabridge background work daemon.
# Copyright 2013 Grigory Petrov
# See LICENSE for details.

import argparse
import datetime
import os
import re
import socket
import sqlite3
import threading
import time
from xmlrpc.server import SimpleXMLRPCServer

import pyparadoxdb

from parabridge import settings


class Worker(threading.Thread):
    _instance_o = None

    def __init__(self):
        super().__init__()
        self._shutdown_f = False
        self._shutdown_o = threading.Event()
        self._cfgCHanged_f = True
        self._results_m = {}
        self._timeReloadLast_o = None

    def run(self):
        while not self._shutdown_f:
            lTasks = []
            if self._cfgCHanged_f:
                lTasks = settings.instance.taskList()
                self._cfgCHanged_f = False
                self._timeReloadLast_o = time.localtime()
            for mTask in lTasks:
                sSrc = os.path.expanduser(mTask["src"])
                sDst = os.path.expanduser(mTask["dst"])
                self.processTask(mTask["guid"], mTask["name"], sSrc, sDst)
            ## Sleep some time so we don't overuse HDD and CPU.
            time.sleep(1)

    def processTask(self, s_guid, s_name, s_src, s_dst):
        def setRes(i_sTxt):
            self._results_m[s_name] = i_sTxt
            return False

        if not os.path.exists(s_src):
            return setRes(f'Path "{s_src}" not found.')
        if not os.path.isdir(s_src):
            return setRes(f'Path "{s_src}" is not a directory.')
        try:
            os.makedirs(os.path.dirname(s_dst))
        except OSError:
            pass

        lSrcFiles = [s_src + os.sep + s for s in os.listdir(s_src)]
        lSrcFiles = [s for s in lSrcFiles if os.path.isfile(s)]
        lSrcFiles = [s for s in lSrcFiles if re.search(r"(?i)\.db$", s)]
        if 0 == len(lSrcFiles):
            return setRes(f'No .db files in "{s_src}".')
        lProcessed = []
        nTotal = len(lSrcFiles)
        with sqlite3.connect(s_dst) as oConn:
            for i, sSrcFile in enumerate(lSrcFiles):
                setRes(f"Processing {i + 1}/{nTotal}")
                if self.processParadoxFile(s_guid, sSrcFile, oConn):
                    lProcessed.append(True)
                if self._shutdown_f:
                    return
                ## Sleep some time so we don't overuse HDD and CPU.
                time.sleep(1)
        sTime = time.strftime("%Y.%m.%d %H:%M:%S")
        nProcessed = len(lProcessed)
        setRes(f"Processed {nProcessed}/{nTotal} at {sTime}.")

    ##x Process individual Paradox |.db| file and synchronize specified
    ##  SQLite database file with it.
    def processParadoxFile(self, s_guid, s_src, o_conn):
        try:
            sFile = os.path.basename(s_src)
            nIndexLast = settings.instance.indexLastGet(s_guid, sFile)
            mArgs = {"shutdown": self._shutdown_o}
            ##  First time parse of this file?
            if nIndexLast is None:
                oDb = pyparadoxdb.open(s_src, **mArgs)
            else:
                mArgs["start"] = nIndexLast + 1
                oDb = pyparadoxdb.open(s_src, **mArgs)
            ##  We can handle only tables that has autoincrement field (if
            ##  such field exists, it will be first for Paradox database. We
            ##  need it to detect updates).
            if len(oDb.fields) < 1 or not oDb.fields[0].isAutoincrement():
                return False
            ##  Table empty or not updated since saved last index.
            if 0 == len(oDb.records):
                return True
            for oRecord in oDb.records:
                nIndex = oRecord.fields[0]
                if nIndexLast is not None and nIndexLast >= nIndex:
                    msg = "Consistency error."
                    raise Exception(msg)
                nIndexLast = nIndex
                self.processParadoxRecord(oDb, oRecord, o_conn, sFile)
            settings.instance.indexLastSet(s_guid, sFile, nIndexLast)
        except pyparadoxdb.Shutdown:
            return False
        return True

    def processParadoxRecord(self, o_db, o_record, o_conn, s_file):
        def FieldName(i_sParadoxName):
            ##! Paradox fields may be named like 'index' that is not a valid
            ##  name for SQLite.
            return f"f_{i_sParadoxName.lower()}"

        def FieldKey(i_sParadoxName):
            return f":{FieldName(i_sParadoxName)}"

        ##! Table name as written in Paradox table file may not be unique among
        ##  multiple files in single Paradox folder. Use file name as table name
        ##  for SQLite.
        mArgs = {
            "name": re.sub(r"(?i)\.db$", "", s_file).lower(),
            "fields": ", ".join([FieldName(o.name) for o in o_db.fields]),
            "values": ", ".join([FieldKey(o.name) for o in o_db.fields]),
        }
        lSignatures = []
        for i, oField in enumerate(o_db.fields):
            sName = FieldName(oField.name)
            ##! Paradox autoincrement field starts from 1, while for SQLite it
            ##  starts from 0 and adding first item with 1 will raise an error.
            ##  As workaround, use non-autoincrement field for SQLite.
            if pyparadoxdb.CField.AUTOINCREMENT == oField.type:
                sSignature = f"{sName} INTEGER"
            else:
                sSignature = f"{sName} {oField.toSqliteType()}"
            lSignatures.append(sSignature)
        mArgs["signature"] = ", ".join(lSignatures)
        sQuery = "CREATE TABLE IF NOT EXISTS {name} ({signature})"
        sQuery = sQuery.format(**mArgs)
        o_conn.execute(sQuery, mArgs)
        sQuery = "INSERT INTO {name} ({fields}) VALUES ({values})"
        sQuery = sQuery.format(**mArgs)
        mArgs = {}
        for i, oField in enumerate(o_db.fields):
            uField = o_record.fields[i]
            lUnsupported = [datetime.time, datetime.date, datetime.datetime]
            if str == type(uField):
                uField = uField.decode("cp1251")
            if type(uField) in lUnsupported:
                ##  SQLite don't have time types, use |ISO 8601| string.
                uField = uField.isoformat()
            mArgs[FieldName(oField.name)] = uField
        o_conn.execute(sQuery, mArgs)

    def shutdown(self):
        self._shutdown_f = True
        ##! After |_shutdown_f| is set to prevent races.
        self._shutdown_o.set()

    @classmethod
    def instance(cls):
        if not cls._instance_o:
            cls._instance_o = Worker()
        return cls._instance_o

    def cfgChanged(self):
        self._cfgCHanged_f = True

    def results(self):
        return self._results_m

    def timeReloadLast(self):
        return self._timeReloadLast_o


class Server(SimpleXMLRPCServer):
    def __init__(self, n_port):
        gAddr = ("localhost", n_port)
        SimpleXMLRPCServer.__init__(self, gAddr, logRequests=False)
        self._shutdown_f = False
        self.register_function(self.stop)
        self.register_function(self.status)
        self.register_function(self.cfgChanged)

    def serve_forever(self, **_):
        while not self._shutdown_f:
            self.handle_request()

    def stop(self):
        self._shutdown_f = True
        return True

    def status(self):
        oTimeReloadLast = Worker.instance().timeReloadLast()
        sMsg = """Daemon is running.
      \tConfiguration reloaded: {}""".format(
            time.strftime("%Y.%m.%d %H:%M:%S", oTimeReloadLast)
        )
        mResults = Worker.instance().results()
        for sKey in sorted(mResults.keys()):
            sMsg += f"\n{sKey}:\n\t {mResults[sKey]}"
        return re.sub("\t", " ", re.sub(" +", " ", sMsg))

    def cfgChanged(self):
        Worker.instance().cfgChanged()
        return True


if __name__ == "__main__":
    settings.instance.init()
    oParser = argparse.ArgumentParser(description="Parabridge daemon")
    oParser.add_argument("port", type=int, help="Port to listen on")
    oArgs = oParser.parse_args()

    Worker.instance().start()
    try:
        Server(oArgs.port).serve_forever()
    except OSError:
        ##  Unable to bind to port if already started.
        pass
    finally:
        Worker.instance().shutdown()
# end main
