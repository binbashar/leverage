"""
    Utilities to obtain relevant files' and directories' locations
"""
from pathlib import Path
from subprocess import run
from subprocess import PIPE
from subprocess import CalledProcessError


class NotARepositoryError(RuntimeError):
    pass


class NoBuildScriptFoundError(RuntimeError):
    pass


def get_working_path():
    """ Return the working directory where the build file is executed from """
    return Path.cwd()

def get_home_path():
    """ Return the current user's home directory """
    return Path("~").expanduser()

def get_root_path():
    """ Return the path to the root of the Git repository.

    Raises:
        NotARepositoryError: If the current directory is not within a git repository.

    Returns:
        pathlib.Path: Root of the repository.
    """
    try:
        root = run(["git", "rev-parse", "--show-toplevel"],
                   stdout=PIPE,
                   stderr=PIPE,
                   check=True,
                   encoding="utf-8").stdout

    except CalledProcessError as exc:
        if "fatal: not a git repository" in exc.stderr:
            raise NotARepositoryError("Not running in a git repository.")

    return Path(root.strip())

def get_account_path():
    """ Return the path to the current account directory """
    root_path = get_root_path()
    cur_path = get_working_path()
    prev_path = cur_path

    # NOTE: currently we only support up to 5 subdir levels. Normally we use
    #       only 2 subdirectories so this should be enough for most cases.
    for _ in range(5):
        if cur_path.absolute() == root_path:
            break

        prev_path = cur_path
        cur_path = cur_path.parent

    return prev_path

def get_global_config_path():
    """ Return the path to the config that is common to all accounts """
    return get_root_path() / "config"

def get_account_config_path():
    """ Return the path to the config of the current account """
    return get_account_path() / "config"

def get_build_script(filename="build.py"):
    """ Get path to the build script containing all tasks to be run.
    Search through the current directory up to the repository's root directory.

    Args:
        filename (str, optional): The name of the build script containing the tasks.
            Defaults to "build.py".

    Raises:
        NoBuildScriptFoundError: If no file with the given name is found either in the
            current directory or any of its parents.

    Returns:
        pathlib.Path: Build script file.
    """
    root_path = get_root_path()
    cur_path = get_working_path()

    while True:
        for cur_file in cur_path.iterdir():
            if cur_file.name == filename:
                return cur_file

        if cur_path == root_path:
            break

        cur_path = cur_path.parent

    raise NoBuildScriptFoundError(f"No file '{filename}' found in the current directory or its parents.")
