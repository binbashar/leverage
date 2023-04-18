import logging

import pytest
from rich.logging import RichHandler

from leverage.logger import get_script_log_level
from leverage.logger import get_verbosity
from leverage.logger import _configure_logger
from leverage.logger import initialize_logger
from leverage.logger import get_tasks_logger
from leverage.logger import BuildFilter
from leverage.logger import _leverage_logger
from leverage.logger import _TASK_LOGGING_FORMAT


DEBUG = logging.getLevelName("DEBUG")
INFO = logging.getLevelName("INFO")
WARNING = logging.getLevelName("WARNING")


@pytest.mark.parametrize("verbose, expected_value", [(True, 3), (False, 2)])
def test_get_script_log_level(click_context, verbose, expected_value):
    with click_context(verbose=verbose):
        log_level = get_script_log_level()

    assert log_level == expected_value


def test_get_verbosity():
    assert get_verbosity(verbose=True) == DEBUG
    assert get_verbosity(verbose=False) == INFO


def test__configure_logger(click_context):
    with click_context(verbose=False):
        logger = logging.getLogger("build")

        _configure_logger(logger)

        assert logger.level == INFO
        assert len(logger.handlers) == 1

        handler = logger.handlers[0]
        assert isinstance(handler, RichHandler)
        assert handler.level == INFO


def test_initialize_logger(with_click_context):
    # Just in case we clear the logger state
    _leverage_logger.handlers = []
    _leverage_logger.setLevel(WARNING)

    @initialize_logger
    def nop():
        pass

    nop()

    assert _leverage_logger.level == DEBUG
    assert len(_leverage_logger.handlers) == 1

    handler = _leverage_logger.handlers[0]
    assert isinstance(handler, RichHandler)
    assert handler.level == DEBUG

    # Just in case we clear the logger state
    _leverage_logger.handlers = []
    _leverage_logger.setLevel(WARNING)


def test_get_tasks_logger(with_click_context):
    logger = get_tasks_logger()

    assert logger.level == DEBUG
    assert len(logger.handlers) == 1

    handler = logger.handlers[0]
    assert handler.level == DEBUG
    assert not handler._log_render.show_level

    filter = handler.filters[0]
    assert isinstance(filter, BuildFilter)
    assert filter._build_script is None

    logger.info("Some message")
    assert logger.handlers[0].filters[0]._build_script == "build.py"

    assert handler.formatter._fmt == _TASK_LOGGING_FORMAT
