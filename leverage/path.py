"""
    Utilities to obtain relevant files' and directories' locations
"""
from pathlib import Path
from subprocess import run
from subprocess import PIPE
from subprocess import CalledProcessError


class NotARepositoryError(RuntimeError):
    pass


def get_working_path():
    """ Get the interpreters current directory.

    Returns:
        str: Current working directory.
    """
    return Path.cwd().as_posix()


def get_home_path():
    """ Get the current user's home directory.

    Returns:
        str: User's home directory.
    """
    return Path.home().as_posix()


def get_root_path():
    """ Get the path to the root of the Git repository.

    Raises:
        NotARepositoryError: If the current directory is not within a git repository.

    Returns:
        str: Root of the repository.
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

    return root.strip()


def get_account_path():
    """ Get the path to the current account directory.

    Returns:
        str: Path to the current account directory.
    """
    root_path = Path(get_root_path())
    cur_path = Path(get_working_path())
    prev_path = cur_path

    # NOTE: currently we only support up to 5 subdir levels. Normally we use
    #       only 2 subdirectories so this should be enough for most cases.
    for _ in range(5):
        if cur_path.resolve() == root_path:
            break

        prev_path = cur_path
        cur_path = cur_path.parent

    return prev_path.as_posix()


def get_global_config_path():
    """ Get the path to the config that is common to all accounts.

    Returns:
        str: Global config file path.
    """
    return f"{get_root_path()}/config"


def get_account_config_path():
    """ Get the path to the config of the current account.

    Returns:
        str: Current config file path.
    """
    return f"{get_account_path()}/config"


def get_build_script_path(filename="build.py"):
    """ Get path to the build script containing all tasks to be run.
    Search through the current directory up to the repository's root directory.

    Args:
        filename (str, optional): The name of the build script containing the tasks.
            Defaults to "build.py".

    Returns:
        str: Build script file path. None if no file with the given name is found or
            the current directory is not a git repository.
    """
    try:
        root_path = Path(get_root_path())
    except NotARepositoryError:
        script = Path(filename)
        return script.absolute().as_posix() if script.exists() else None

    cur_path = Path(get_working_path())

    while True:
        build_script = list(cur_path.glob(filename))

        if build_script:
            return build_script[0].as_posix()

        if cur_path == root_path:
            break

        cur_path = cur_path.parent
