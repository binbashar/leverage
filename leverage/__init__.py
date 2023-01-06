"""
    Binbash Leverage Command-line tool.
"""
#pylint: disable=wrong-import-position

__version__ = "0.0.0"
__toolbox_version__ = "1.2.7-0.1.0"

import sys
from shutil import which

if which("git") is None: #pragma: no cover
    print("No git installation found in the system. Exiting.")
    sys.exit(1)

from leverage import logger
from leverage.tasks import task
from leverage.leverage import leverage
