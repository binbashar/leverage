from pathlib import Path
import os, git

def get_working_path():
    """Return the working directory where the build file is executed from"""
    return os.getcwd()

def get_home_path():
    """Return the current user's home directory"""
    return os.path.expanduser("~")

def get_root_path():
    """Return the path to the root of the Git repository"""
    git_repo = git.Repo(get_working_path(), search_parent_directories=True)
    return git_repo.git.rev_parse('--show-toplevel')

def get_account_path():
    """Return the path to the current account directory"""
    root_path = Path(get_root_path())
    cur_path = Path(get_working_path())
    prev_path = cur_path
    
    #
    # NOTE: currently we only support up to 5 subdir levels. Normally we use
    #       only 2 subdirs so this should be enough for most cases.
    #
    for i in range(5):
        if (cur_path.absolute() == root_path): break
        prev_path = cur_path
        cur_path = Path(cur_path).parent
    return str(prev_path)

def get_global_config_path():
    """Return the path to the config that is common to all accounts"""
    return "%s/config" % get_root_path()

def get_account_config_path():
    """Return the path to the config of the current account"""
    return "%s/config" % get_account_path()
