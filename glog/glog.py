import os
import sys
import logging
import time
import multiprocessing
from datetime import datetime, timedelta
from queue import Empty
from logging.handlers import TimedRotatingFileHandler, QueueHandler, QueueListener
import inspect
import json
import requests


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

        if not os.path.exists(logs_base_dir):
            return  # No logs to clean up

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
                            # Remove month and year directories if empty
                            if not os.listdir(month_path):
                                os.rmdir(month_path)
                            if not os.listdir(year_path):
                                os.rmdir(year_path)
                        except Exception as e:
                            print(f"Error deleting old log directory '{day_path}': {e}")

class GLogger:
    LOG_LEVELS = [logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL]

    def __init__(
        self,
        backupCount=7,
        is_multiprocessing=False,
        log_dir=None,
        print_logs=False,
        log_retention_days=7,
        telegram_alert=False,
        telegram_config_file='telegram_alert_config.json'
    ):
        self.is_multiprocessing = is_multiprocessing
        self.loggers = {}
        self.print_logs = print_logs
        self.log_retention_days = log_retention_days
        self.telegram_alert = telegram_alert
        self.telegram_config_file = telegram_config_file
        self.telegram_bot_token = None
        self.telegram_user_ids = []

        # Determine the default log directory
        if log_dir is None:
            self.log_dir = self.get_main_script_directory()
        else:
            self.log_dir = log_dir

        # Initialize Telegram bot if telegram_alert is True
        if self.telegram_alert:
            self.load_telegram_config()

        if self.is_multiprocessing:
            self.log_queue = multiprocessing.Queue()
            self.setup_logging_queue_listener()
            self.glog = self.enqueue_log_message
        else:
            self.glog = self.direct_log_message

        for level in self.LOG_LEVELS:
            self.loggers[level] = self.setup_logger_for_level(level, backupCount)

    def load_telegram_config(self):
        """Load Telegram bot token and user IDs from the configuration file."""
        try:
            with open(self.telegram_config_file, 'r') as f:
                config = json.load(f)
            bot_token = config.get('bot_token')
            user_ids = config.get('user_ids', [])

            if not bot_token or not user_ids:
                print("Telegram configuration file is missing 'bot_token' or 'user_ids'.")
                self.telegram_alert = False
                return

            self.telegram_bot_token = bot_token
            self.telegram_user_ids = user_ids
        except Exception as e:
            print(f"Failed to load Telegram configuration: {e}")
            self.telegram_alert = False

    def get_main_script_directory(self):
        """Get the directory of the main script that is running."""
        try:
            # Get the path of the main script
            main_script_path = os.path.abspath(sys.modules['__main__'].__file__)
            return os.path.dirname(main_script_path)
        except (AttributeError, KeyError):
            # If we can't get the main script directory, default to the current working directory
            return os.getcwd()

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
        # Include caller_filename in the formatter
        formatter = logging.Formatter('%(asctime)s - %(caller_filename)s - %(levelname)s - %(message)s')
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
            # Get caller's frame and filename
            frame = inspect.currentframe()
            caller_frame = frame.f_back
            filename = os.path.basename(caller_frame.f_code.co_filename)
            lineno = caller_frame.f_lineno
            # Create a LogRecord with extra data
            record = logger.makeRecord(
                logger.name,
                level,
                caller_frame.f_code.co_filename,
                lineno,
                message,
                args=(),
                exc_info=None,
                extra={'caller_filename': filename}
            )
            self.log_queue.put(record)

            # Send Telegram alert if applicable
            if self.telegram_alert and level >= logging.ERROR:
                self.send_telegram_alert(message, level)

    def direct_log_message(self, message, level=logging.DEBUG):
        logger = self.loggers.get(level)
        if logger:
            # Get caller's frame and filename
            frame = inspect.currentframe()
            caller_frame = frame.f_back
            filename = os.path.basename(caller_frame.f_code.co_filename)
            # Log with extra data
            logger.log(level, message, extra={'caller_filename': filename})

            # Send Telegram alert if applicable
            if self.telegram_alert and level >= logging.ERROR:
                self.send_telegram_alert(message, level)

    def send_telegram_alert(self, message, level):
        """Send a log message as a Telegram alert to the specified users via HTTP requests."""
        if not self.telegram_bot_token or not self.telegram_user_ids:
            return  # Telegram bot is not initialized

        level_name = logging.getLevelName(level)
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        alert_message = f"{timestamp} - {level_name} - {message}"

        url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"

        for user_id in self.telegram_user_ids:
            payload = {
                'chat_id': user_id,
                'text': alert_message
            }
            try:
                response = requests.post(url, data=payload, timeout=10)
                if response.status_code != 200:
                    print(f"Failed to send Telegram alert to user {user_id}: {response.text}")
            except requests.RequestException as e:
                print(f"Failed to send Telegram alert to user {user_id}: {e}")

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
        if self.is_multiprocessing and hasattr(self, 'queue_listener'):
            self.queue_listener.stop()


# Example usage
if __name__ == "__main__":
    # Testing
    g_logger = GLogger(
        is_multiprocessing=False,
        backupCount=60,
        print_logs=True,
        log_retention_days=7,
        telegram_alert=True,
        telegram_config_file='telegram_config.json'
    )

    # Log some messages
    g_logger.glog("This is an info message.", logging.INFO)
    g_logger.glog("This is an error message.", logging.ERROR)
    g_logger.glog("This is a critical message.", logging.CRITICAL)

    print("End")
    g_logger.stop_logging_queue_listener()
