"""
    Env variables loading utility.
"""
from pathlib import Path

from yaenv.core import Env

from .path import get_root_path
from .path import get_working_path


def load(config_filename="build.env"):
    """ Load all .env files with the given name in the current directory an all of its parents up to
    the repository root directory and store them in a dictionary.
    Files are traversed from parent to child as to allow values in deeper directories to override possible
    previously existing values.
    Terminates if not ran within a git repository.

    Args:
        config_filename (str, optional): .env filenames to load. All must bear the same name. Defaults to "build.env".

    Raises:
        NotARepositoryError: Whenever the function is ran outside a git repository.

    Returns:
        dict: All variables defined in the loaded .env files.
    """
    root_path = Path(get_root_path())
    cur_path = Path(get_working_path())

    config_files_paths = []
    config_dict = {}

    while True:
        for cur_file in cur_path.iterdir():
            if cur_file.name == config_filename:
                print(f"[DEBUG] Found config file: {cur_file.resolve().as_posix()}")

                config_files_paths.append(cur_file.resolve().as_posix())

        if cur_path == root_path:
            break

        cur_path = cur_path.parent

    # Reverse the list of config files so it can be traversed from parent to child directory
    config_files_paths = config_files_paths[::-1]

    for config_file_path in config_files_paths:
        config_file = Env(config_file_path)

        for key, val in config_file:
            config_dict[key] = val

    return config_dict
