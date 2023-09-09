# SPDX-FileCopyrightText: 2023-present Edouard Choinière <27212526+echoix@users.noreply.github.com>
#
# SPDX-License-Identifier: GPL-3.0-only
import sys

def main():
    import parabridge.cli
    sys.exit(parabridge.cli.parabridgecli())

if __name__ == "__main__":
    main()