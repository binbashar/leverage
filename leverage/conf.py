"""
    Env variables loading utility.
"""
from pathlib import Path

from yaenv.core import Env

from leverage import logger
from leverage.path import get_root_path
from leverage.path import get_working_path


ENV_CONFIG_FILE = "build.env"


def load(config_filename=ENV_CONFIG_FILE):
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
    # TODO: Return an Env object instead of a dictionary, to be able to leverage its type casting utilities
    config_dict = {}

    while True:
        env_file = list(cur_path.glob(config_filename))

        if env_file:
            env_file = env_file[0].as_posix()
            logger.debug(f"Found config file {env_file}")

            config_files_paths.append(env_file)

        if cur_path == root_path:
            break

        cur_path = cur_path.parent

    # Traverse config files from parent to child
    for config_file_path in reversed(config_files_paths):
        config_file = Env(config_file_path)

        for key, val in config_file:
            config_dict[key] = val

    return config_dict
