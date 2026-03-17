import os
from dotenv import load_dotenv

load_dotenv()

# ── KuveytTürk İnternet Şubesi ────────────────────────────
KUVEYTTURK_URL = "https://isube.kuveytturk.com.tr/Login/InitialLogin"
KUVEYTTURK_TC = os.getenv("KUVEYTTURK_TC", "")
KUVEYTTURK_PASSWORD = os.getenv("KUVEYTTURK_PASSWORD", "")
KUVEYTTURK_PHONE = os.getenv("KUVEYTTURK_PHONE", "")  # 905xxxxxxxxx

# ── Doğrulama ──────────────────────────────────────────────
PHONE_VERIFICATION_TIMEOUT = 120   # saniye — mobil onay bekleme süresi
PHONE_VERIFICATION_CHECK_INTERVAL = 3

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
