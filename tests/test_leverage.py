import sys
from importlib import util

from leverage.leverage import _get_tasks
from leverage.leverage import _load_build_script

from .conftest import BUILD_SCRIPT


def test__load_build_script():
    module = _load_build_script(build_script=BUILD_SCRIPT)

    # All the important bits are extracted
    assert module["name"] == BUILD_SCRIPT.name
    assert len(module["tasks"]) == 1
    assert module["tasks"][0].name == "hello"
    assert module["__DEFAULT__"] is None

    # Module is globally available
    assert BUILD_SCRIPT.stem in sys.modules
    del sys.modules[BUILD_SCRIPT.stem]


def test__get_tasks():
    spec = util.spec_from_file_location(name=BUILD_SCRIPT.stem,
                                        location=BUILD_SCRIPT)
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)

    tasks = _get_tasks(module=module)
    assert len(tasks) == 1
    assert tasks[0].name == "hello"
