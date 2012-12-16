"""
Lightweight Python Build Tool

"""

__authors__ = ['Raghunandan Rao', "Calum J. Eadie"]
__license__ = "MIT License"
__contact__ = "https://github.com/rags/pynt"

import inspect
import argparse
import logging
import os
import re

_CREDIT_LINE = "Powered by pynt - A Lightweight Python Build Tool."
_LOGGING_FORMAT = "[ %(name)s - %(message)s ]"
_TASK_PATTERN = re.compile("^([^\[]+)(\[([^\]]*)\])?$")
#"^([^\[]+)(\[([^\],=]*(,[^\],=]+)*(,[^\],=]+=[^\],=]+)*)\])?$"
def build(module,args):
    """
    Build the specified module with specified arguments.
    
    @type module: module
    @type args: list of arguments
    """
    
    # Build the command line.
    parser = _create_parser()

    # Parse arguments.
    args = parser.parse_args(args)

    # Run task and all it's dependancies.
    if args.list_tasks:
        print_tasks(module)
    elif not args.tasks:
        parser.print_help()
        print "\n"
        print_tasks(module)
    else:
        _run_from_task_names(module,args.tasks)

def print_tasks(module):
    # Get all tasks.
    tasks = _get_tasks(module)
    
    # Build task_list to describe the tasks.
    task_list = "Tasks in build file %s:" % module.__file__
    name_width = _get_max_name_length(module)+4
    task_help_format = "\n  {0:<%s} {1: ^10} {2}" % name_width
    for task in tasks:
        task_list += task_help_format.format(task.name, "[Ignored]" if task.ignored else '', task.doc)
    print task_list + "\n\n"+_CREDIT_LINE

def _run_from_task_names(module,task_names):
    """
    @type module: module
    @type task_name: string
    @param task_name: Task name, exactly corresponds to function name.
    """

    # Create logger.
    logger = _get_logger(module)

    completed_tasks = set([])
    for task_name in task_names:
        task, args, kwargs= _get_task(module,task_name)
        _run(module, logger, task, completed_tasks, True, args, kwargs)

def _get_task(module, name):
    # Get all tasks.
    match = _TASK_PATTERN.match(name)
    if not match:
        raise Exception("Invalid task argument %s" % name)
    task_name, _, args_str = match.groups()
    tasks = _get_tasks(module)
    args, kwargs= _parse_args(args_str)
    if hasattr(module, task_name):
        return getattr(module, task_name), args, kwargs
    matching_tasks = filter(lambda task: task.name.startswith(task_name), tasks)
        
    if not matching_tasks:
        raise Exception("task should be one of " +
                        ', '.join([task.name for task in tasks]))
    if len(matching_tasks) == 1:
        return matching_tasks[0], args, kwargs
    raise Exception("Conflicting matches %s for task %s " % (
        ', '.join([task.name for task in matching_tasks]), task_name
    ))

def _parse_args(args_str):
    args = []
    kwargs = {}
    if not args_str:
        return args, kwargs
    arg_parts = args_str.split(",")

    for i, part in enumerate(arg_parts):
        if "=" in part:
            key, value = [_str.strip() for _str in part.split("=")]
            if key in kwargs:
                raise Exception("duplicate keyword argument %s" % part)
            kwargs[key] = value
        else:
            if len(kwargs) > 0:
                raise Exception("Non keyword arg %s cannot follows a keyword arg %s"
                                % (part, arg_parts[i - 1]))
            args.append(part.strip())
    return args, kwargs
    
def _run(module, logger, task, completed_tasks, from_command_line = False, args = None, kwargs = None):
    """
    @type module: module
    @type logging: Logger
    @type task: Task
    @type completed_tasts: set Task
    @rtype: set Task
    @return: Updated set of completed tasks after satisfying all dependancies.
    """

    # Satsify dependancies recursively. Maintain set of completed tasks so each
    # task is only performed once.
    for dependancy in task.dependancies:
        completed_tasks = _run(module,logger,dependancy,completed_tasks)

    # Perform current task, if need to.
    if from_command_line or task not in completed_tasks:

        if task.ignored:
        
            logger.info("Ignoring task \"%s\"" % task.name)
            
        else:

            logger.info("Starting task \"%s\"" % task.name)

            try:
                # Run task.
                task(*(args or []),**(kwargs or {}))
            except:
                logger.critical("Error in task \"%s\"" % task.name)
                logger.critical("Aborting build")
                raise
            
            logger.info("Completed task \"%s\"" % task.name)
        
        completed_tasks.add(task)
    
    return completed_tasks

def _create_parser():
    """
    @rtype: argparse.ArgumentParser
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("tasks", help="perform specified task and all it's dependancies",
                        metavar="task", nargs = '*')
    parser.add_argument('-l', '--list-tasks', help = "List the tasks",
                        action =  'store_true')
    
    return parser
        
# Abbreviate for convenience.
#task = _TaskDecorator
def task(*dependencies, **options):
    for i, dependency in enumerate(dependencies):
        if not Task.is_task(dependency):
                if inspect.isfunction(dependency):
                    # Throw error specific to the most likely form of misuse.
                    if i == 0:
                        raise Exception("Replace use of @task with @task().")
                    else:
                        raise Exception("%s is not a task. Each dependancy should be a task." % dependency)
                else:
                    raise Exception("%s is not a task." % dependency)

    def decorator(fn):
        return Task(fn, dependencies, options)
    return decorator

class Task(object):
    
    def __init__(self, func, dependancies, options):
        """
        @type func: 0-ary function
        @type dependancies: list of Task objects
        """
        self.func = func
        self.name = func.__name__
        self.doc = inspect.getdoc(func) or ''
        self.dependancies = dependancies
        self.ignored =  bool(options.get('ignore', False))
        
    def __call__(self,*args,**kwargs):
        self.func.__call__(*args,**kwargs)
    
    @classmethod
    def is_task(cls,obj):
        """
        Returns true is an object is a build task.
        """
        return isinstance(obj,cls)
    
def _get_tasks(module):
    """
    Returns all functions marked as tasks.
    
    @type module: module
    """
    # Get all functions that are marked as task and pull out the task object
    # from each (name,value) pair.
    return [member[1] for member in inspect.getmembers(module,Task.is_task)]
    
def _get_max_name_length(module):
    """
    Returns the length of the longest task name.
    
    @type module: module
    """
    return max([len(task.name) for task in _get_tasks(module)])
    
def _get_logger(module):
    """
    @type module: module
    @rtype: logging.Logger
    """

    # Create Logger
    logger = logging.getLogger(os.path.basename(module.__file__))
    logger.setLevel(logging.DEBUG)

    # Create console handler and set level to debug
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)

    # Create formatter
    formatter = logging.Formatter(_LOGGING_FORMAT)

    # Add formatter to ch
    ch.setFormatter(formatter)

    # Add ch to logger
    logger.addHandler(ch)

    return logger
