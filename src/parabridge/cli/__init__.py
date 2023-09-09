# SPDX-FileCopyrightText: Copyright 2013 Grigory Petrov
# SPDX-FileCopyrightText: 2023-present Edouard Choinière <27212526+echoix@users.noreply.github.com>
#
# SPDX-License-Identifier: GPL-3.0-only
#
# parabridge command-line entry point.
# Copyright 2013 Grigory Petrov
# See LICENSE for details.

import click

from parabridge.__about__ import __version__

import xmlrpc.client

import subprocess
import os
import socket
import logging

from parabridge import info
from parabridge import settings

HELP_APP = """Paradox to SQLite bridge. This tool monitors specified
  Paradox database and reflects all changes to specified SQLite database
  that can be used by any application that has problems with Paradox."""
HELP_START = """Starts background process that will monitor Paradox
  databse."""
HELP_STOP = """Stops background process that was previously started with
  'start'."""
HELP_STATUS = """Shows current background process status."""
HELP_TASK_ADD = """Adds task with specified name (name can be used later
  to manage tasks), path to source Paradox database directory ('~' will
  be expanded) and path to destination SQLite database file ('~' will
  be expanded)."""
HELP_TASK_DEL = """Deletes task with specified name."""
HELP_TASK_LIST = """Displays list of added tasks."""

click.echo(__version__)
click.echo(__name__)

@click.group(context_settings={"help_option_names": ["-h", "--help"]}, invoke_without_command=False, help=HELP_APP)
@click.version_option(version=__version__, prog_name="parabridge")
def parabridgecli():
    pass


@click.command(help=HELP_START)
def start():
    sFile = os.path.join(os.path.dirname(__file__), "../parabridge_daemon.py")
    subprocess.Popen(['python', sFile, str(info.COMM_PORT)])


@click.command(help=HELP_STOP)
def stop():
    try:
        oSrv = xmlrpc.client.ServerProxy(info.COMM_ADDR)
        oSrv.stop()
    except socket.error:
        pass


@click.command(help=HELP_STATUS)
def status():
    try:
        oSrv = xmlrpc.client.ServerProxy(info.COMM_ADDR)
        click.echo(oSrv.status())
    except socket.error:
        click.echo("Daemon is not running.")


@click.command("task_add", help=HELP_TASK_ADD)
@click.argument('task_name')
@click.argument('task_src')
@click.argument('task_dst')
def task_add(m_args):
    sName = m_args['task_name']
    sSrc = m_args['task_src']
    sDst = m_args['task_dst']
    if not settings.instance.taskAdd(sName, sSrc, sDst):
        logging.warning("Already has '{0}' task".format(sName))


@click.command("task_del", help=HELP_TASK_DEL)
def task_del(m_args):
    if not settings.instance.taskDelByName(m_args['task_name']):
        logging.warning("No task named '{0}'".format(m_args['task_name']))


@click.command("task_list", help=HELP_TASK_LIST)
def task_list():
    lTasks = settings.instance.taskList()
    if 0 == len(lTasks):
        click.echo("Tasks list is empty.")
        return
    for mTask in lTasks:
        click.echo("{0}\n  Source: {1}\n  Destination: {2}".format(mTask['name'], mTask['src'], mTask['dst']))


parabridgecli.add_command(start)
parabridgecli.add_command(stop)
parabridgecli.add_command(status)
parabridgecli.add_command(task_add)
parabridgecli.add_command(task_del)
parabridgecli.add_command(task_list)
