import os
import time
import requests
from datetime import datetime
from config.settings import (
    SCREENSHOTS_DIR,
    SCREENSHOT_ON_ERROR,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
)
from utils.logger import get_logger

log = get_logger(__name__)


def take_screenshot(driver, prefix: str = "error") -> str | None:
    """Ekran görüntüsü alır ve dosya yolunu döner."""
    if not SCREENSHOT_ON_ERROR:
        return None
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(SCREENSHOTS_DIR, f"{prefix}_{timestamp}.png")
    try:
        driver.save_screenshot(filepath)
        log.info(f"Screenshot kaydedildi: {filepath}")
        return filepath
    except Exception as e:
        log.error(f"Screenshot alınamadı: {e}")
        return None


def send_telegram_message(message: str) -> bool:
    """Telegram'a mesaj gönderir."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram bilgileri eksik, mesaj gönderilemedi.")
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
        }
        resp = requests.post(url, json=payload, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        log.error(f"Telegram mesaj hatası: {e}")
        return False


def retry(max_attempts: int = 3, delay: float = 2.0):
    """Fonksiyonu belirtilen sayıda tekrar dener."""

    def decorator(func):
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exc = e
                    log.warning(
                        f"{func.__name__} başarısız (deneme {attempt}/{max_attempts}): {e}"
                    )
                    if attempt < max_attempts:
                        time.sleep(delay)
            raise last_exc

        return wrapper

    return decorator


def format_price(price: float) -> str:
    """Fiyatı TL formatında döner."""
    return f"{price:,.2f} TL".replace(",", "X").replace(".", ",").replace("X", ".")


def format_quantity(qty: int) -> str:
    """Adeti formatlar."""
    return f"{qty:,}".replace(",", ".")
