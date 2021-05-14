"""
    Binbash Leverage Command-line tool.
"""

__version__ = "0.0.18"
__license__ = "MIT License"
__contact__ = "http://github.com/binbashar/"

import sys
import pkgutil
from shutil import which

from .task import task
from .leverage import leverage


if which("git") is None:
    print("No git installation found in the system. Exiting.")
    sys.exit(1)


__path__ = pkgutil.extend_path(__path__, __name__)

__all__ = ["task"]
