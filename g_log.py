import os
import logging
import time
import psutil
import multiprocessing

import datetime as dt

from queue import Empty, Full
from logging.handlers import RotatingFileHandler, MemoryHandler


glob_start = time.time()

class CustomFormatter(logging.Formatter):
    def format(self, record):
        record_time = dt.datetime.fromtimestamp(record.created)
        record.asctime = record_time.strftime('%Y-%m-%d %H:%M:%S.%ff')
        return super(CustomFormatter, self).format(record)

class LogWorker(multiprocessing.Process):
    VALID_LOG_LEVELS = {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}

    def __init__(self, log_queue, parent_pid):
        super(LogWorker, self).__init__()
        self.logger_initialized = False
        self.log_queue = log_queue
        self.parent_pid = parent_pid
        self.logger = logging.getLogger("custom_logger")
        self.current_date = dt.datetime.now().date()
        # self.initialize_logger()

    def run(self):
        if not self.logger_initialized:
            self.initialize_logger()
            self.logger_initialized = True
        while True:
            if not self.is_parent_alive():
                break
            try:
                log_data = self.log_queue.get()
                if log_data is None:
                    break
                self.process_log_data(log_data)
            except Empty:
                continue

    def process_log_data(self, log_data):
        global glob_start
        # print(f"Logging process log_data:\n{log_data}")
        # print("Temp handerels check:", self.logger.handlers)
        if self.log_queue.qsize() == 0:
            print("Finished logging queue")
            glob_end = time.time()
            print(glob_end - glob_start)

        level =     log_data.get("level", "INFO")
        message =   log_data.get("message", "")
        timestamp = log_data.get("timestamp", time.time())

        if dt.datetime.fromtimestamp(timestamp).date() != self.current_date:
            # print("--------------- Date triggerd roll ---------------")
            self.rollover()
            self.initialize_logger()
            self.current_date = dt.datetime.fromtimestamp(timestamp).date()

        if level in self.VALID_LOG_LEVELS:
            record = logging.LogRecord("custom_logger", getattr(logging, level, logging.INFO), "", 0, message, None, None)
            # print(record)
            record.created = timestamp  # Set the timestamp
            # print(record)
            # print("Handlers at the time of logging:", self.logger.handlers)
            self.logger.handle(record)
        else:
            raise ValueError(f"Invalid log level '{level}'. Valid levels are: {', '.join(self.VALID_LOG_LEVELS)}.")

    def setup_log_handler(self, log_level, file_path, formatter, buffer_capacity=500):
        # Create the RotatingFileHandler
        rotating_handler = RotatingFileHandler(file_path, maxBytes=256 * 1024 * 1024, backupCount=50)
        rotating_handler.setLevel(log_level)
        rotating_handler.setFormatter(formatter)
        rotating_handler.namer = self.custom_namer

        # Wrap the RotatingFileHandler with MemoryHandler
        memory_handler = MemoryHandler(capacity=buffer_capacity, target=rotating_handler)
        memory_handler.setLevel(log_level)
        self.logger.addHandler(memory_handler)

    def initialize_logger(self):
        try:
            now = dt.datetime.now()
            year, month, day = now.strftime("%Y"), now.strftime("%b"), now.strftime("%d")
            log_dir_path = os.path.join("Logs", year, month, day)

            if not os.path.exists(log_dir_path):
                os.makedirs(log_dir_path)

            log_file_paths = {
                "DEBUG":    os.path.join(log_dir_path, "Debug.txt"),
                "INFO":     os.path.join(log_dir_path, "Info.txt"),
                "WARNING":  os.path.join(log_dir_path, "Warning.txt"),
                "ERROR":    os.path.join(log_dir_path, "Error.txt"),
                "CRITICAL": os.path.join(log_dir_path, "Critical.txt")
            }

            # print(log_file_paths)
            self.logger.setLevel(logging.DEBUG)
            self.logger.handlers.clear()

            # formatter = logging.Formatter('%(asctime)s.%(msecs)06d --- [%(levelname)s] --- %(message)s',
            #                               datefmt='%H:%M:%S')

            formatter = CustomFormatter('%(asctime)s.%(msecs)03d --- [%(levelname)s] --- %(message)s',
                                          datefmt='%H:%M:%S')

            for level, file_path in log_file_paths.items():
                self.setup_log_handler(getattr(logging, level), file_path, formatter)


        except Exception as e:
            print(f"Error setting up logger: {e}")
            raise

    def custom_namer(self, default_name):
        temp_start = time.time()
        dir_name, file_name = os.path.split(default_name)
        file_root, file_ext = os.path.splitext(file_name)

        file_root = file_root.replace(".txt", "")

        num = 1
        new_name = os.path.join(dir_name, f"{file_root}{num}.txt")
        while os.path.exists(new_name):
            num += 1
            new_name = os.path.join(dir_name, f"{file_root}{num}.txt")

        temp_end = time.time()
        return new_name

    def rollover(self):
        for handler in self.logger.handlers:
            if isinstance(handler, RotatingFileHandler):
                handler.doRollover()

    def is_parent_alive(self):
        """ Check if the parent process is still alive using psutil """
        try:
            parent = psutil.Process(self.parent_pid)
            return parent.is_running()
        except psutil.NoSuchProcess:
            return False

class Glogger:
    def __init__(self):
        self.log_queue = multiprocessing.Queue(-1)
        self.log_worker = LogWorker(self.log_queue, os.getpid())
        self.log_worker.start()

    def log(self, level, message):

        log_data = {
            "timestamp":    time.time(),
            "level":        level,
            "message":      message
        }
        try:
            # print(f"Main process log_data:\n{log_data}")
            self.log_queue.put_nowait(log_data)
        except Full:
            pass

    def stop_logging(self):
        try:
            self.log_queue.put_nowait(None)
        except Full:
            print("log_queue FULL....")

        self.log_worker.join()


if __name__ == '__main__':
    glogger = Glogger()
    
    start = time.time()

    glogger.log(level="DEBUG", message="First row")

    for i in range(10**5):
        # print(f"\n\nStarted itter: {i}")
        glogger.log(level="DEBUG", message="Debug only log example")

    end = time.time()
    print(end - start)
