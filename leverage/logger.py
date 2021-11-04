"""
    Logging utilities.
"""
import logging
from functools import wraps

from rich.console import Console
from rich.logging import RichHandler
from click import get_current_context


_TASK_LOGGING_FORMAT = ("[bold light_yellow3][ %(build_script)s -[/bold light_yellow3]"
                        " %(message)s [bold light_yellow3]][/bold light_yellow3]")
_TIME_FORMAT = lambda time: f"[{time:%H:%M:%S}.{time.microsecond//1000:03}]"

_leverage_logger = logging.getLogger("leverage")


# Use the same console for the logging handler and any other special cases like
# spinners, tables or progress bars.
console = Console()


def get_mfa_script_log_level():
    """ Get the verbosity level from the application state and map it to the MFA script log level.
    Logging level in the MFA script is implemented as:
        ERROR = 1
        INFO = 2
        DEBUG = 3

    Returns:
        int: Logging level as defined in the MFA script.
    """
    mfa_log_level = {
        logging.ERROR: 1,
        logging.INFO: 2,
        logging.DEBUG: 3
    }

    verbosity = get_current_context().obj.verbosity
    return mfa_log_level[verbosity]


def get_verbosity(verbose):
    """ Transform the given verbosity level into the corresponding logging level.

    Args:
        verbose (bool): Whether the logging should be verbose or not

    Returns:
        int: Logging level
    """
    return logging.DEBUG if verbose else logging.INFO


def _configure_logger(logger, show_level=True):
    """ Provide the given logger with the most basic configuration possible to be used.

    Args:
        logger (logging.Logger): Logger to be configured
        show_level (bool): Whether to display the logging level in the record. Defaults to True
    """
    state = get_current_context().obj

    level = state.verbosity
    logger.setLevel(level)

    logger.propagate = False

    handler = RichHandler(level=level,
                          console=console,
                          show_level=show_level,
                          show_path=False,
                          enable_link_path=False,
                          markup=True,
                          rich_tracebacks=True,
                          tracebacks_show_locals=True,
                          log_time_format=_TIME_FORMAT)

    logger.handlers = []
    logger.addHandler(handler)


def initialize_logger(log_func):
    """ Decorator to initialize the global logger before logging a message if it wasn't already initialized. """
    @wraps(log_func)
    def wrapper(*args, **kwargs):
        if not _leverage_logger.handlers:
            _configure_logger(logger=_leverage_logger)
        log_func(*args, **kwargs)

    return wrapper


@initialize_logger
def debug(message): #pragma: no cover
    """ Utility debug function to ease logging. """
    _leverage_logger.debug(message)


@initialize_logger
def info(message): #pragma: no cover
    """ Utility info function to ease logging. """
    _leverage_logger.info(message)


@initialize_logger
def warning(message): #pragma: no cover
    """ Utility warning function to ease logging. """
    _leverage_logger.warning(message)


@initialize_logger
def error(message): #pragma: no cover
    """ Utility error function to ease logging. """
    _leverage_logger.error(message)


@initialize_logger
def critical(message): #pragma: no cover
    """ Utility critical function to ease logging. """
    _leverage_logger.critical(message)


@initialize_logger
def exception(message, exc_info=False): #pragma: no cover
    """ Utility exception function to ease logging. """
    _leverage_logger.exception(message, exc_info=exc_info)


class BuildFilter(logging.Filter):
    """ Filter class to add additional info to a log record. """
    def __init__(self):
        super().__init__()
        self._build_script = None

    def filter(self, record):
        if self._build_script is None:
            state = get_current_context().obj
            self._build_script = state.module.name

        record.build_script = self._build_script
        return True


def get_tasks_logger():
    """ Provide a logger specially configured to display the status of tasks execution. """
    logger = logging.getLogger("build")
    _configure_logger(logger=logger, show_level=False)

    logfilter = BuildFilter()
    logger.handlers[0].addFilter(logfilter)

    formatter = logging.Formatter(_TASK_LOGGING_FORMAT)
    logger.handlers[0].setFormatter(formatter)

    return logger
