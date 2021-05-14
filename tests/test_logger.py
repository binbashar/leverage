import logging

from leverage.logger import get_logger
from leverage.logger import BuildFilter
from leverage.logger import _TASK_LOGGING_FORMAT
from leverage.logger import attach_build_handler


def test_get_logger(click_context):
    with click_context():
        logger = get_logger("build")

        assert logger.name == "build"
        assert len(logger.handlers) == 1
        handler = logger.handlers[0]
        assert isinstance(handler, logging.StreamHandler)
        assert handler.level == logging.getLevelName("DEBUG")
        assert handler.formatter is None

        assert not logger.filters


def test_attach_build_handler(click_context):
    with click_context():
        logger = get_logger()

        attach_build_handler(logger=logger, build_script_name="build.py")

        assert len(logger.handlers) == 1
        handler = logger.handlers[0]
        assert isinstance(handler, logging.StreamHandler)
        assert handler.level == logging.getLevelName("DEBUG")

        logfilter = handler.filters[0]
        assert isinstance(logfilter, BuildFilter)
        assert logfilter._build_script == "build.py"

        formatter = handler.formatter
        assert formatter._fmt == _TASK_LOGGING_FORMAT
