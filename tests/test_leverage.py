import re
import pytest
from pathlib import Path
from shutil import copyfile

from leverage.leverage import _print_version
from leverage.leverage import build as leverage


_BUILD_SCRIPTS = Path("./tests/build_scripts/").resolve()


def test_print_version(caplog):
    with pytest.raises(SystemExit) as sysexit:
        _print_version()

    assert sysexit.value.code == 0
    version = caplog.messages[0]
    assert re.match(r"^leverage \d+.\d+.\d+$", version)


def test_leverage_in_git_repository(pytester):
    pytester.syspathinsert(Path().cwd().parent)
    pytester.run("git", "init")

    root_dir = pytester.path
    build_script = root_dir / "build.py"
    build_script.write_text("""
from leverage import task

@task()
def hello():
    \"\"\" Say hello. \"\"\"
    print(\"Hello\")
"""
    )

    test_file = pytester.makepyfile(
        """
        import re
        import pytest

        from leverage.leverage import build as leverage

        def test_build(capsys):
            leverage(['-l'])
            output = capsys.readouterr().out
            assert re.match(r'Tasks in build file `build.py`:'
                            r'\\n\\n  hello  \\t Say hello. \\n\\n'
                            r'Powered by Leverage.+', output)
        """
    )
    result = pytester.runpytest(test_file)
    assert result.ret == 0


def test_leverage_not_in_git_repository(pytester):
    pytester.syspathinsert(Path().cwd().parent)

    test_file = pytester.makepyfile(
        """
        import re
        import pytest

        from leverage.leverage import build as leverage

        def test_build(caplog):
            with pytest.raises(SystemExit) as sysexit:
                leverage(['-l'])

            assert sysexit.value.code == 1

            output = caplog.messages[0]
            print(output)
            assert re.match(r'Not running in a git repository. Exiting.', output)
        """
    )
    result = pytester.runpytest(test_file)
    assert result.ret == 0


def test_leverage_with_build_script(dir_structure, capsys):
    root_dir, _ = dir_structure
    copyfile(_BUILD_SCRIPTS / "simple_build.py", root_dir / "simple_build.py")

    leverage(["-f", "simple_build.py", "-l"])

    captured = capsys.readouterr()
    output = captured.out
    assert re.match(r"Tasks in build file `simple_build.py`:"
                    r"\n\n  hello  \t Say hello. \n\n"
                    r"Powered by Leverage.+", output)


def test_leverage_with_no_build_script(dir_structure, caplog):
    with pytest.raises(SystemExit) as sysexit:
        leverage(["-l"])

    assert sysexit.value.code == 1
    output = caplog.messages[0]
    assert re.match(r"No file 'build.py' found in the current directory or its parents. Exiting.", output)


def test_leverage_no_escaped_blank_in_task_arguments(dir_structure, caplog):
    root_dir, _ = dir_structure
    (root_dir / "build.py").touch()

    with pytest.raises(SystemExit) as sysexit:
        leverage(["task1[arg1,", "arg2]", "task2"])

    assert sysexit.value.code == 1
    output = caplog.messages[0]
    assert re.match(r"Malformed task argument in `task1\[arg1,`. Exiting.", output)
