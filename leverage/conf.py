from pathlib import Path
from os import listdir
from yaenv.core import Env
from . import path

_CONFIG_FILENAME = "build.env"

def load():
    root_path = Path(path.get_root_path())
    cur_path = Path(path.get_working_path())
    config_files_paths = []
    config_dict = {}

    # Go from current dir up to the root dir
    while True:
        for cur_file in listdir(cur_path):
            # If a build config file is found, append it to the list
            if cur_file == _CONFIG_FILENAME:
                print("[DEBUG] Found config file: %s/%s \n" % (cur_path, cur_file))
                config_files_paths.append("%s/%s" % (cur_path, cur_file))

        # Keep looking until we reach the root path
        if (cur_path == root_path): break

        # Move to parent dir
        cur_path = Path(cur_path).parent

    # Reverse the list of config files so it can be traversed from parent to child directory
    config_files_paths = config_files_paths[::-1]

    # Go through each config file in the list
    for config_file_path in config_files_paths:
        config_file = Env(config_file_path)

        # Add entry to the config dict
        for key, val in config_file:
            config_dict[key] = val

    return config_dict
