import os
import logging
import multiprocessing
from datetime import datetime, timedelta
from logging.handlers import TimedRotatingFileHandler, QueueHandler, QueueListener


class CustomTimedRotatingFileHandler(TimedRotatingFileHandler):
    def __init__(self, level_name, when, interval, backupCount, log_dir, log_retention_days):
        self.level_name = level_name.lower()
        self.log_dir = log_dir
        self.log_retention_days = log_retention_days
        filename = self.get_daily_log_file_path()
        super().__init__(filename, when, interval, backupCount, encoding='utf8', delay=False)

    def get_daily_log_file_path(self):
        today = datetime.now().date()
        log_dir = os.path.join(
            self.log_dir,
            'Logs',
            str(today.year),
            today.strftime('%B'),
            today.strftime('%d')
        )
        os.makedirs(log_dir, exist_ok=True)
        return os.path.join(log_dir, f'{self.level_name}.log')

    def doRollover(self):
        super().doRollover()
        self.cleanup_old_logs()

    def cleanup_old_logs(self):
        """Delete log directories older than the retention period."""
        cutoff_date = datetime.now().date() - timedelta(days=self.log_retention_days)
        logs_base_dir = os.path.join(self.log_dir, 'Logs')

        # Walk through the directory structure: Logs/YYYY/MMMM/DD
        for year_dir in os.listdir(logs_base_dir):
            year_path = os.path.join(logs_base_dir, year_dir)
            if not os.path.isdir(year_path) or not year_dir.isdigit():
                continue

            for month_dir in os.listdir(year_path):
                month_path = os.path.join(year_path, month_dir)
                if not os.path.isdir(month_path):
                    continue

                for day_dir in os.listdir(month_path):
                    day_path = os.path.join(month_path, day_dir)
                    if not os.path.isdir(day_path):
                        continue

                    # Construct the directory date
                    try:
                        dir_date = datetime.strptime(f"{year_dir}-{month_dir}-{day_dir}", "%Y-%B-%d").date()
                    except ValueError:
                        continue  # Skip directories that don't match the date format

                    # Delete directories older than cutoff_date
                    if dir_date < cutoff_date:
                        try:
                            # Remove all files in the directory
                            for filename in os.listdir(day_path):
                                file_path = os.path.join(day_path, filename)
                                if os.path.isfile(file_path):
                                    os.remove(file_path)
                            # Remove the day directory
                            os.rmdir(day_path)
                            # If the month directory is empty after removing the day directory, remove it
                            if not os.listdir(month_path):
                                os.rmdir(month_path)
                            # If the year directory is empty after removing the month directory, remove it
                            if not os.listdir(year_path):
                                os.rmdir(year_path)
                        except Exception as e:
                            # Handle exceptions (e.g., permission issues) as needed
                            print(f"Error deleting old log directory '{day_path}': {e}")


class GLogger:
    LOG_LEVELS = [logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL]

    def __init__(self, backupCount=7, is_multiprocessing=False, log_dir=None, print_logs=False, log_retention_days=7):
        self.is_multiprocessing = is_multiprocessing
        self.loggers = {}
        self.log_dir = log_dir or os.getcwd()
        self.print_logs = print_logs
        self.log_retention_days = log_retention_days

        if self.is_multiprocessing:
            self.log_queue = multiprocessing.Queue()
            self.setup_logging_queue_listener()
            self.glog = self.enqueue_log_message
        else:
            self.glog = self.direct_log_message

        for level in self.LOG_LEVELS:
            self.loggers[level] = self.setup_logger_for_level(level, backupCount)

    def setup_logger_for_level(self, level, backupCount):
        level_name = logging.getLevelName(level)
        logger = logging.getLogger(f'g_logger_{level_name}')
        logger.setLevel(level)

        if logger.hasHandlers():
            logger.handlers.clear()

        # File handler with log retention
        file_handler = CustomTimedRotatingFileHandler(
            level_name=level_name,
            when='midnight',
            interval=1,
            backupCount=backupCount,
            log_dir=self.log_dir,
            log_retention_days=self.log_retention_days
        )
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)

        # Add handlers based on multiprocessing
        if self.is_multiprocessing:
            queue_handler = QueueHandler(self.log_queue)
            logger.addHandler(queue_handler)
        else:
            logger.addHandler(file_handler)

        # Add console handler if print_logs is True
        if self.print_logs:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(level)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)

        return logger

    def enqueue_log_message(self, message, level=logging.DEBUG):
        logger = self.loggers.get(level)
        if logger:
            logger.log(level, message)

    def direct_log_message(self, message, level=logging.DEBUG):
        logger = self.loggers.get(level)
        if logger:
            logger.log(level, message)

    def setup_logging_queue_listener(self):
        # Collect handlers from all loggers
        handlers = []
        for level in self.LOG_LEVELS:
            level_name = logging.getLevelName(level)
            logger = self.loggers.get(level)
            if logger:
                for handler in logger.handlers[:]:
                    if isinstance(handler, QueueHandler):
                        continue
                    handlers.append(handler)
                    logger.removeHandler(handler)
        self.queue_listener = QueueListener(self.log_queue, *handlers)
        self.queue_listener.start()

    def stop_logging_queue_listener(self):
        if self.is_multiprocessing and self.queue_listener:
            self.queue_listener.stop()


# Example usage
if __name__ == "__main__":
    # Testing
    g_logger = GLogger(is_multiprocessing=False, backupCount=7, print_logs=True, log_retention_days=7)

    # Log some messages
    g_logger.glog("This is an info message.", logging.INFO)
    g_logger.glog("This is an error message.", logging.ERROR)
    g_logger.glog("This is a debug message.", logging.DEBUG)

    print("End")
    g_logger.stop_logging_queue_listener()
