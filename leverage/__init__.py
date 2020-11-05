"""
Lightweight Python Build Tool
"""

__version__ = "0.0.3"
__license__ = "MIT License"
__contact__ = "http://github.com/binbashar/"

from ._leverage import task, main
import pkgutil

__path__ = pkgutil.extend_path(__path__,__name__)

__all__ = ["task",  "main"]
