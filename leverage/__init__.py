"""
    Binbash Leverage Command-line tool.
"""

# pylint: disable=wrong-import-position

__version__ = "0.0.0"
__toolbox_version__ = "1.3.5-0.2.0"

MINIMUM_VERSIONS = {
    "TERRAFORM": "1.3.5",
    "TOOLBOX": "0.2.1",  # update to 0.2.1 once released, we require awscli >= 2.22 now
}

import sys
from shutil import which

if which("git") is None:  # pragma: no cover
    print("No git installation found in the system. Exiting.")
    sys.exit(1)

from leverage import logger
from leverage.tasks import task
from leverage.leverage import leverage
