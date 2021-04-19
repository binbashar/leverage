import pytest
import logging

from leverage.logger import get_logger
from leverage.logger import BuildFilter
from leverage.logger import _TASK_LOGGING_FORMAT
from leverage.logger import _attach_build_handler


def test_get_logger():
    logger = get_logger(name="leverage", level="WARNING")

    assert len(logger.handlers) == 1
    handler = logger.handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    assert handler.level == logging.getLevelName("WARNING")
    assert handler.formatter is None

    assert not logger.filters


def test__attach_build_handler():
    logger = logging.getLogger("leverage")

    _attach_build_handler(logger=logger, build_script_name="build.py", level="WARNING")

    assert len(logger.handlers) == 1
    handler = logger.handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    assert handler.level == logging.getLevelName("WARNING")

    logfilter = handler.filters[0]
    assert isinstance(logfilter, BuildFilter)
    assert logfilter._build_script == "build.py"

    formatter = handler.formatter
    assert formatter._fmt == _TASK_LOGGING_FORMAT
