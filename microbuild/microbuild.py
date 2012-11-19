"""
Lightweight Python Build Tool
"""

__author__ = "Calum J. Eadie"
__license__ = "MIT License"
__contact__ = "https://github.com/CalumJEadie/microbuild"

import inspect
import argparse
import logging
import sys
import traceback
import os
import re

_CREDIT_LINE = "Powered by microbuild - A Lightweight Python Build Tool."
_LOGGING_FORMAT = "[ %(name)s - %(message)s ]"
_TASK_PATTERN = re.compile("^([^\[]+)(\[([^\]]*)\])?$")
def build(module,args):
    """
    Build the specified module with specified arguments.
    
    @type module: module
    @type args: list of arguments
    """
    
    # Build the command line.
    parser = _create_parser(module)

    # Parse arguments.
    args = parser.parse_args(args)

    # Run task and all it's dependancies.
    _run_from_task_names(module,args.task)
    
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
    matching_tasks = filter(lambda task: task.__name__.startswith(task_name), tasks)
        
    if not matching_tasks:
        raise Exception("task should be one of " +
                        ', '.join([task.__name__ for task in tasks]))
    if len(matching_tasks) == 1:
        return matching_tasks[0], args, kwargs
    raise Exception("Conflicting matches %s for task %s " % (
        ', '.join([task.__name__ for task in matching_tasks]), task_name
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

        if task.is_ignorable():
        
            logger.info("Ignoring task \"%s\"" % task.__name__)
            
        else:

            logger.info("Starting task \"%s\"" % task.__name__)

            try:
                # Run task.
                task(*(args or []),**(kwargs or {}))
            except:
                logger.critical("Error in task \"%s\"" % task.__name__)
                traceback.print_exc()
                logger.critical("Build aborted")
                sys.exit()
            
            logger.info("Completed task \"%s\"" % task.__name__)
        
        completed_tasks.add(task)
    
    return completed_tasks

def _create_parser(module):
    """
    @type module: module
    @rtype: argparse.ArgumentParser
    """

    # Get all tasks.
    tasks = _get_tasks(module)
    
    # Build epilog to describe the tasks.
    epilog = "tasks:"
    name_width = _get_max_name_length(module)+4
    task_help_format = "\n  {0.__name__:<%s} {0.__doc__}" % name_width
    for task in tasks:
        epilog += task_help_format.format(task)
    epilog += "\n\n"+_CREDIT_LINE
    
    # Build parser.
    # Use RawDescriptionHelpFormatter so epilog is not linewrapped.
    parser = argparse.ArgumentParser(
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("task",help="perform specified task and all it's dependancies",metavar="task", nargs = '+')
    
    return parser

class TaskDecorationException(Exception):
    """
    Throw when task decoration is used incorrectly.
    """
    pass

class _TaskDecorator(object):
    
    def __init__(self,*decorator_args):
        """
        Performs validation on use of @task annotation and captures dependancies.
        
        This constructor is called immediately after decorated function is defined.
        
        To simply implementation of __call__ use of @task() when there a task
        has no dependancies instead of @task is enfored.
        
        This is neccessary because the use case for __call__ is very different depending
        on whether @task or @task() is used.
        
        See http://www.artima.com/weblogs/viewpost.jsp?thread=240845 for more information.
        
        @type decorator_args: tuple
        @param decorator_args: Three cases depending on which form of @task is used.
            - @task then expect (function)
            - @task() then expect ()
            - @task(task1,...,taskN) then expect (task1,...,taskN)
        @throws TaskDecorationException
        """
        
        # Validate arguments.
        # Need to check that either @task() or @task(task1,...,taskN) has been used.
        # If @task or @task(arg1,...,argN) where some arg is not a task then the build script
        # is poorly formed.
        
        # Iterate over by index so we can provide error messages appropriate to the
        # likely form of misuse.
        decorator_args = list(decorator_args)
        for i in range(0,len(decorator_args)):
            if not Task.is_task(decorator_args[i]):
                if inspect.isfunction(decorator_args[i]):
                    # Throw error specific to the most likely form of misuse.
                    if i == 0:
                        raise TaskDecorationException("Replace use of @task with @task().")
                    else:
                        raise TaskDecorationException("%s is not a task. Each dependancy should be a task." % decorator_args[i])
                else:
                    raise TaskDecorationException("%s is not a task." % decorator_args[i])
        
        # Capture dependancies.
        self.dependancies = decorator_args
        
    def __call__(self, func):
        """
        @type func: function
        @param func: Function being decorated.
        """
        return Task(func,self.dependancies)
        
# Abbreviate for convenience.
task = _TaskDecorator

def ignore(obj):
    """
    Decorator to specify that a task should be ignored.
    
    @type obj: function or Task, depending on order @ignore and @task used
    """
    obj.ignorable = True
    return obj
        
class Task(object):
    
    def __init__(self,func,dependancies):
        """
        @type func: 0-ary function
        @type dependancies: list of Task objects
        """
        self.func = func
        self.__name__ = func.__name__
        self.__doc__ = inspect.getdoc(func)
        self.__module__ = func.__module__
        self.dependancies = dependancies
        
    def __call__(self,*args,**kwargs): self.func.__call__(*args,**kwargs)
    
    @classmethod
    def is_task(cls,obj):
        """
        Returns true is an object is a build task.
        """
        return isinstance(obj,cls)
        
    def is_ignorable(self):
        """
        Returns true if task can be ignored.
        """
        return ( hasattr(self,'ignorable') and self.ignorable == True ) or ( hasattr(self.func,'ignorable') and self.func.ignorable == True )
    
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
    return max([len(task.__name__) for task in _get_tasks(module)])
    
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
