"""
Selenium Browser yönetimi.
Headless Chrome/Chromium ile DigitalOcean droplet üzerinde çalışır.
"""

import os
import shutil
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from config.settings import HEADLESS, IMPLICIT_WAIT, PAGE_LOAD_TIMEOUT
from utils.logger import get_logger

log = get_logger(__name__)


class Browser:
    """Selenium WebDriver sarmalayıcısı."""

    def __init__(self):
        self.driver = None

    def start(self) -> webdriver.Chrome:
        """Chrome tarayıcısını başlatır."""
        log.info("Tarayıcı başlatılıyor...")

        options = Options()

        if HEADLESS:
            options.add_argument("--headless=new")

        # DigitalOcean droplet için gerekli argümanlar
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--remote-debugging-port=9222")

        # Snap Chromium için binary yolu
        import shutil
        for binary_path in [
            "/snap/bin/chromium",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            "/usr/bin/google-chrome",
        ]:
            if shutil.which(binary_path) or os.path.exists(binary_path):
                options.binary_location = binary_path
                log.info(f"Chromium binary: {binary_path}")
                break

        # Bot algılamayı zorlaştır
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        # User-Agent
        options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        )

        try:
            # Önce sistem ChromeDriver'ı dene (droplet'te apt ile kurulu)
            try:
                service = Service("/usr/bin/chromedriver")
                self.driver = webdriver.Chrome(service=service, options=options)
                log.info("Sistem ChromeDriver kullanılıyor.")
            except Exception:
                # webdriver-manager ile otomatik indir
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=options)
                log.info("webdriver-manager ChromeDriver kullanılıyor.")

            self.driver.implicitly_wait(IMPLICIT_WAIT)
            self.driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)

            # navigator.webdriver flag'ini gizle
            self.driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {
                    "source": """
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                """
                },
            )

            log.info("Tarayıcı başarıyla başlatıldı.")
            return self.driver

        except Exception as e:
            log.error(f"Tarayıcı başlatılamadı: {e}")
            raise

    def quit(self):
        """Tarayıcıyı kapatır."""
        if self.driver:
            try:
                self.driver.quit()
                log.info("Tarayıcı kapatıldı.")
            except Exception as e:
                log.warning(f"Tarayıcı kapatılırken hata: {e}")
            finally:
                self.driver = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.quit()
        return False
