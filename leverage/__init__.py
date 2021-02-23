"""
BinBash Reference Architecture Task Runner
"""

__version__ = "0.0.10"
__license__ = "MIT License"
__contact__ = "http://github.com/binbashar/"

from .leverage import task, main
import pkgutil

__path__ = pkgutil.extend_path(__path__, __name__)

__all__ = ["task",  "main"]
