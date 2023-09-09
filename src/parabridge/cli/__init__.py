# SPDX-FileCopyrightText: 2023-present Edouard Choinière <27212526+echoix@users.noreply.github.com>
#
# SPDX-License-Identifier: GPL-3.0-only
import click

from parabridge.__about__ import __version__


@click.group(context_settings={"help_option_names": ["-h", "--help"]}, invoke_without_command=True)
@click.version_option(version=__version__, prog_name="parabridge")
def parabridge():
    click.echo("Hello world!")
