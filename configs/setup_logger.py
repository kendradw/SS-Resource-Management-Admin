import logging
import sys
import os

# def get_resource_path(relative_path):
#     """Resolves path to bundled or script-relative resource"""
#     if hasattr(sys, '_MEIPASS'):
#         return os.path.join(sys._MEIPASS, relative_path)
#     return os.path.join(os.path.abspath("."), relative_path)

def get_log_file_path():
    base_dir = os.getenv("APPDATA") or os.path.abspath(".")
    log_dir = os.path.join(base_dir, "DCT_RM_Tools")
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, "log.log")

class ColoredFormatter(logging.Formatter):
    """Formatter for applying ANSI colors to log messages for console output."""
    COLORS = {
        logging.DEBUG: "\033[0;33m",   # Yellow
        logging.INFO: "\033[0;32m",    # Green
        logging.WARNING: "\033[0;35m", # Purple
        logging.ERROR: "\033[0;31m",   # Red
        logging.CRITICAL: "\033[1;31m" # Bright Red
    }

    def format(self, record):
        formatted_message = super().format(record)
        log_color = self.COLORS.get(record.levelno, "")
        reset_color = "\033[0m"
        return f"{log_color}{formatted_message}{reset_color}"

def setup_logger(name=None, level=logging.INFO, log_to_file=True, file_path = None):
    """
    Set up a logger with:
    - Colored output for the console.
    - Plain text logs for files.
    
    Args:
        name (str): Logger name (usually __name__).
        level (int): Logging level.
        log_to_file (bool): Whether to also log to a file.
        file_path (str): Log file path (relative to script or bundle).
    
    Returns:
        logging.Logger: Configured logger.
    """
    
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    if logger.hasHandlers():
        logger.handlers.clear()

    # Console Handler (Colored)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_formatter = ColoredFormatter(
        '%(asctime)s [%(levelname)s] %(filename)s - %(name)s - %(funcName)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File Handler (Plain Text, No Colors)
    if log_to_file:
        if file_path is None:
            file_path = get_log_file_path()
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        file_handler = logging.FileHandler(file_path)
        file_handler.setLevel(level)
        plain_formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(filename)s - %(name)s - %(funcName)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(plain_formatter)
        logger.addHandler(file_handler)
    

    return logger
