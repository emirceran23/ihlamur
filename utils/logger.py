import logging
import os
from datetime import datetime
from config.settings import LOG_LEVEL, LOG_DIR


def get_logger(name: str) -> logging.Logger:
    """Modül bazlı logger oluşturur."""
    os.makedirs(LOG_DIR, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    if not logger.handlers:
        # Konsol handler
        console = logging.StreamHandler()
        console.setLevel(logging.DEBUG)
        console_fmt = logging.Formatter(
            "%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
            datefmt="%H:%M:%S",
        )
        console.setFormatter(console_fmt)
        logger.addHandler(console)

        # Dosya handler
        today = datetime.now().strftime("%Y-%m-%d")
        file_handler = logging.FileHandler(
            os.path.join(LOG_DIR, f"ihlamur_{today}.log"),
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_fmt = logging.Formatter(
            "%(asctime)s │ %(levelname)-7s │ %(name)s │ %(funcName)s:%(lineno)d │ %(message)s"
        )
        file_handler.setFormatter(file_fmt)
        logger.addHandler(file_handler)

    return logger
