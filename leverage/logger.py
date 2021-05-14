"""
    Logging utilities.
"""
import logging

from click import get_current_context


_TASK_LOGGING_FORMAT = "[ %(build_script)s - %(message)s ]"


# TODO: Consider creating a custom handler to use click.echo to emit messages instead StreamHandler


def get_logging_level():
    """ Define logging level based on whether the verbose option was given or not

    Returns:
        int: logging.DEBUG or logging.INFO
    """
    context = get_current_context()
    verbose = context.obj["verbose"]

    return logging.DEBUG if verbose else logging.INFO


def get_logger(name="leverage"):
    """ Build a logger with the given name and log level

    Args:
        name (str): Logger name.

    Returns:
        logger: configured logger
    """
    level = get_logging_level()

    logger = logging.getLogger(name)
    logger.setLevel(level)

    handler = logging.StreamHandler()
    handler.setLevel(level)

    logger.handlers = []
    logger.addHandler(handler)

    return logger


class BuildFilter(logging.Filter):
    """ Filter class to add additional info to a log record. """
    def __init__(self, build_script):
        super().__init__()
        self._build_script = build_script

    def filter(self, record):
        record.build_script = self._build_script
        return True


def attach_build_handler(logger, build_script_name):
    """ Attach a filter to a logger as to add build script information to every log record.
    All previously attached StreamHandlers are discarded from the logger.

    Args:
        logger (logger): The logger to which the filter should be attached.
        build_script_name (str): Name of the build script file.
        level (str, optional): Log level name it can be any of the defined in the standard library.
            Defaults to "INFO".
    """
    level = get_logging_level()

    logger.handlers = [handler
                       for handler in logger.handlers
                       if not isinstance(handler, logging.StreamHandler)]

    handler = logging.StreamHandler()
    handler.setLevel(level)

    logfilter = BuildFilter(build_script=build_script_name)
    handler.addFilter(logfilter)

    formatter = logging.Formatter(_TASK_LOGGING_FORMAT)
    handler.setFormatter(formatter)

    logger.addHandler(handler)
