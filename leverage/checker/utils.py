import logging
import time


class TimeIt:
    """
    Context manager to measure and log the execution time of a block of code.
    It uses the logger provided, or defaults to the root logger if none is provided.

    Args:
    - task_name (str): A name for the task to help identify it in the logs.
    - logger (logging.Logger): Optional. A logger object to use for logging the time.
    """

    def __init__(self, task_name="Unnamed Task", logger=None):
        self.task_name = task_name
        self.logger = logger if logger is not None else logging.getLogger(__name__)
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self  # You can return anything that might be useful, but here we don't need to

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed_time = time.time() - self.start_time
        hours, remainder = divmod(elapsed_time, 3600)
        minutes, seconds = divmod(remainder, 60)
        milliseconds = (elapsed_time - int(elapsed_time)) * 1000
        human_readable = "{:02}:{:02}:{:02}.{:03}".format(int(hours), int(minutes), int(seconds), int(milliseconds))
        self.logger.debug(f"{self.task_name} took {human_readable} (hh:mm:ss.mmm)")
