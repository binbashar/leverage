"""
    Logging utilities.
"""
import logging


_TASK_LOGGING_FORMAT = "[ %(build_script)s - %(message)s ]"


def get_logger(name, level, format_string=None):
    """ Build a logger with the given name and log level

    Args:
        name (str): Logger name.
        level (str): Logging level can be one of the names specified in
            the standard library.

    Returns:
        logger: configured logger
    """
    level = logging.getLevelName(level)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    handler = logging.StreamHandler()
    handler.setLevel(level)

    if format_string is not None:
        formatter = logging.Formatter(format_string)
        handler.setFormatter(formatter)

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


def _attach_build_handler(logger, build_script_name, level="INFO"):
    """ Attach a filter to a logger as to add build script information to every log record.
    All previously attached StreamHandlers are discarded from the logger.

    Args:
        logger (logger): The logger to which the filter should be attached.
        build_script_name (str): Name of the build script file.
        level (str, optional): Log level name it can be any of the defined in the standard library.
            Defaults to "INFO".
    """

    level = logging.getLevelName(level)

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
