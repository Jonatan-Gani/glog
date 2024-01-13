import os
import logging
import time
import multiprocessing

from datetime import datetime
from queue import Empty
from logging.handlers import TimedRotatingFileHandler


class CustomTimedRotatingFileHandler(TimedRotatingFileHandler):
    def __init__(self, level_name, when, interval, backupCount):
        # self.base_log_dir = base_log_dir
        self.level_name = level_name.lower()
        filename = self.get_daily_log_file_path()
        super().__init__(filename, when, interval, backupCount, encoding='utf8', delay=False)

    def get_daily_log_file_path(self):
        today = datetime.now().date()
        log_dir = os.path.join('Logs', str(today.year), today.strftime('%B'), today.strftime('%d'))
        os.makedirs(log_dir, exist_ok=True)
        return os.path.join(log_dir, f'{self.level_name}.log')

    def doRollover(self):
        """
        Override doRollover to modify the log file path dynamically based on the date
        """
        self.baseFilename = self.get_daily_log_file_path()
        super().doRollover()


class GLogger:
    LOG_LEVELS = [logging.DEBUG, logging.ERROR, logging.CRITICAL, logging.INFO, logging.WARNING]

    def __init__(self, backupCount=7, is_multiprocessing=False):
        self.is_multiprocessing = is_multiprocessing
        self.loggers = {}
        self.log_queue = multiprocessing.Queue() if is_multiprocessing else None
        self.log_listener_process = None

        if self.is_multiprocessing:
            self.main_alive_event = multiprocessing.Event()
            self.main_alive_event.set()  # Initially set the event

            self.start_log_listener_process()
            self.glog = self.enqueue_log_message  # Set glog to enqueue log messages
        else:
            self.glog = self.direct_log_message  # Set glog to log messages directly

        for level in self.LOG_LEVELS:
            self.loggers[level] = self.setup_logger_for_level(logging.getLevelName(level), backupCount)

    def setup_logger_for_level(self, level_name, backupCount):
        logger = logging.getLogger(f'g_logger_{level_name}')
        logger.setLevel(level_name)

        handler = CustomTimedRotatingFileHandler(level_name, when='midnight', interval=1,
                                                 backupCount=backupCount)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)

        logger.addHandler(handler)
        return logger

    def enqueue_log_message(self, message, level=logging.DEBUG):
        timestamp = time.time()  # Capture the current timestamp
        self.log_queue.put((level, message, timestamp))

    def direct_log_message(self, message, level=logging.DEBUG):
        if level in self.loggers:
            self.loggers[level].log(level, message)

    def start_log_listener_process(self):
        self.log_listener_process = multiprocessing.Process(target=self.log_listener)
        self.log_listener_process.daemon = True
        self.log_listener_process.start()

    def log_listener(self):
        while self.main_alive_event.is_set() or not self.log_queue.empty():
            try:
                while not self.log_queue.empty():
                    level, message, timestamp = self.log_queue.get_nowait()
                    if level in self.loggers:
                        self.loggers[level].log(level, self.format_log_message(timestamp, message))
            except Empty:
                pass
            except Exception as e:
                pass

    def format_log_message(self, timestamp, message):
        formatted_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))
        return f"{formatted_time} - {message}"

    def stop_log_listener_process(self):
        if self.log_listener_process:
            self.log_listener_process.terminate()
            self.log_listener_process = None


# Example usage
if __name__ == "__main__":
    g_logger = GLogger(is_multiprocessing=False, backupCount=60)

    g_logger.glog("This is an info message.", logging.INFO)
    g_logger.glog("This is an error message.", logging.ERROR)
    g_logger.glog(message="This is an debug message.")

    print("End")
    exit()
