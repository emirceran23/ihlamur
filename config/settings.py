import os
from dotenv import load_dotenv

load_dotenv()

# ── TradePlus ──────────────────────────────────────────────
TRADEPLUS_URL = "https://tradeplus.com.tr"
TRADEPLUS_TC = os.getenv("TRADEPLUS_TC", "")
TRADEPLUS_PASSWORD = os.getenv("TRADEPLUS_PASSWORD", "")
TRADEPLUS_ACCOUNT_NO = os.getenv("TRADEPLUS_ACCOUNT_NO", "")  # Müşteri No
TRADEPLUS_PHONE = os.getenv("TRADEPLUS_PHONE", "")             # Kayıtlı cep tel (905xxxxxxxxx)

# ── Browser ────────────────────────────────────────────────
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
IMPLICIT_WAIT = 10          # saniye
PAGE_LOAD_TIMEOUT = 30      # saniye
SCREENSHOT_ON_ERROR = os.getenv("SCREENSHOT_ON_ERROR", "true").lower() == "true"
SCREENSHOTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "screenshots")

# ── Logging ────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")

# ── Telegram ───────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ── İşlem Limitleri ───────────────────────────────────────
MAX_ORDER_AMOUNT = 50000     # TL - tek seferde max işlem tutarı
MAX_DAILY_TRADES = 20        # günlük max işlem sayısı

# ── Telefon Doğrulama ─────────────────────────────────────
PHONE_VERIFICATION_TIMEOUT = 120  # saniye - çağrı merkezi doğrulaması için max bekleme
PHONE_VERIFICATION_CHECK_INTERVAL = 3  # saniye - URL kontrol sıklığı
