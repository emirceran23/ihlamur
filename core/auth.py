"""
KuveytTürk TradePlus Giriş / Çıkış modülü.
"""

import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from config.settings import TRADEPLUS_URL, TRADEPLUS_TC, TRADEPLUS_PASSWORD
from utils.logger import get_logger
from utils.helpers import take_screenshot, retry

log = get_logger(__name__)


class Auth:
    """TradePlus kimlik doğrulama işlemleri."""

    def __init__(self, driver):
        self.driver = driver
        self.wait = WebDriverWait(driver, 15)
        self.is_logged_in = False

    @retry(max_attempts=3, delay=3.0)
    def login(self) -> bool:
        """
        TradePlus'a giriş yapar.

        TradePlus web sayfasının yapısına göre selector'lar
        güncellenmelidir. İlk çalıştırmada screenshot alıp
        doğru elementleri tespit etmemiz gerekecek.
        """
        log.info("TradePlus'a giriş yapılıyor...")
        self.driver.get(TRADEPLUS_URL)
        time.sleep(3)  # sayfanın tam yüklenmesini bekle

        try:
            # ── Adım 1: TC Kimlik No girişi ──────────────────────
            # NOT: Selector'lar TradePlus arayüzüne göre güncellenmeli
            tc_input = self._find_element(
                possible_selectors=[
                    (By.ID, "tckn"),
                    (By.ID, "tcKimlikNo"),
                    (By.NAME, "tckn"),
                    (By.NAME, "tcKimlikNo"),
                    (By.CSS_SELECTOR, "input[placeholder*='T.C.']"),
                    (By.CSS_SELECTOR, "input[placeholder*='Kimlik']"),
                    (By.CSS_SELECTOR, "input[type='text']"),
                    (By.XPATH, "//input[contains(@placeholder, 'T.C.')]"),
                    (By.XPATH, "//input[contains(@placeholder, 'Kimlik')]"),
                ],
                description="TC Kimlik No alanı",
            )

            if tc_input:
                tc_input.clear()
                tc_input.send_keys(TRADEPLUS_TC)
                log.info("TC Kimlik No girildi.")
            else:
                take_screenshot(self.driver, "login_tc_not_found")
                raise Exception("TC Kimlik No alanı bulunamadı!")

            # ── Adım 2: Şifre girişi ─────────────────────────────
            password_input = self._find_element(
                possible_selectors=[
                    (By.ID, "password"),
                    (By.ID, "sifre"),
                    (By.NAME, "password"),
                    (By.NAME, "sifre"),
                    (By.CSS_SELECTOR, "input[type='password']"),
                    (By.XPATH, "//input[@type='password']"),
                ],
                description="Şifre alanı",
            )

            if password_input:
                password_input.clear()
                password_input.send_keys(TRADEPLUS_PASSWORD)
                log.info("Şifre girildi.")
            else:
                take_screenshot(self.driver, "login_password_not_found")
                raise Exception("Şifre alanı bulunamadı!")

            # ── Adım 3: Giriş butonuna tıkla ─────────────────────
            login_btn = self._find_element(
                possible_selectors=[
                    (By.ID, "loginButton"),
                    (By.CSS_SELECTOR, "button[type='submit']"),
                    (By.XPATH, "//button[contains(text(), 'Giriş')]"),
                    (By.XPATH, "//button[contains(text(), 'GİRİŞ')]"),
                    (By.XPATH, "//input[@type='submit']"),
                    (By.CSS_SELECTOR, ".login-button"),
                    (By.CSS_SELECTOR, ".btn-login"),
                ],
                description="Giriş butonu",
            )

            if login_btn:
                login_btn.click()
                log.info("Giriş butonuna tıklandı.")
            else:
                take_screenshot(self.driver, "login_button_not_found")
                raise Exception("Giriş butonu bulunamadı!")

            # ── Adım 4: Giriş sonrası doğrulama ──────────────────
            time.sleep(5)
            self._verify_login()
            self.is_logged_in = True
            log.info("✅ TradePlus'a başarıyla giriş yapıldı!")
            return True

        except Exception as e:
            take_screenshot(self.driver, "login_error")
            log.error(f"Giriş başarısız: {e}")
            raise

    def _find_element(self, possible_selectors: list, description: str):
        """
        Birden fazla selector ile element bulmayı dener.
        TradePlus arayüz değişikliklerinde esnek kalır.
        """
        for by, value in possible_selectors:
            try:
                element = self.wait.until(
                    EC.presence_of_element_located((by, value))
                )
                log.debug(f"{description} bulundu: {by}={value}")
                return element
            except TimeoutException:
                continue
        log.warning(f"{description} hiçbir selector ile bulunamadı!")
        return None

    def _verify_login(self):
        """Giriş başarılı mı kontrol eder."""
        # Sayfanın URL'sinin değişip değişmediğini kontrol et
        current_url = self.driver.current_url
        log.info(f"Giriş sonrası URL: {current_url}")

        # Hata mesajı var mı kontrol et
        error_selectors = [
            (By.CSS_SELECTOR, ".error-message"),
            (By.CSS_SELECTOR, ".alert-danger"),
            (By.XPATH, "//*[contains(text(), 'hatalı')]"),
            (By.XPATH, "//*[contains(text(), 'Hatalı')]"),
        ]
        for by, value in error_selectors:
            try:
                error_el = self.driver.find_element(by, value)
                if error_el.is_displayed():
                    raise Exception(f"Giriş hatası: {error_el.text}")
            except Exception:
                continue

        # Screenshot al (debug için)
        take_screenshot(self.driver, "login_success")

    def logout(self):
        """TradePlus'tan çıkış yapar."""
        if not self.is_logged_in:
            return

        try:
            logout_btn = self._find_element(
                possible_selectors=[
                    (By.XPATH, "//a[contains(text(), 'Çıkış')]"),
                    (By.XPATH, "//button[contains(text(), 'Çıkış')]"),
                    (By.CSS_SELECTOR, ".logout"),
                    (By.CSS_SELECTOR, "[title='Çıkış']"),
                ],
                description="Çıkış butonu",
            )
            if logout_btn:
                logout_btn.click()
                log.info("Çıkış yapıldı.")
            self.is_logged_in = False
        except Exception as e:
            log.warning(f"Çıkış sırasında hata: {e}")
            self.is_logged_in = False

    def explore_page(self) -> dict:
        """
        Sayfa yapısını keşfeder. İlk çalıştırmada
        doğru selector'ları bulmak için kullanılır.
        """
        log.info("Sayfa yapısı keşfediliyor...")
        take_screenshot(self.driver, "explore")

        info = {
            "url": self.driver.current_url,
            "title": self.driver.title,
            "inputs": [],
            "buttons": [],
            "links": [],
        }

        # Tüm input'ları listele
        inputs = self.driver.find_elements(By.TAG_NAME, "input")
        for inp in inputs:
            info["inputs"].append({
                "type": inp.get_attribute("type"),
                "id": inp.get_attribute("id"),
                "name": inp.get_attribute("name"),
                "placeholder": inp.get_attribute("placeholder"),
                "class": inp.get_attribute("class"),
            })

        # Tüm butonları listele
        buttons = self.driver.find_elements(By.TAG_NAME, "button")
        for btn in buttons:
            info["buttons"].append({
                "text": btn.text,
                "id": btn.get_attribute("id"),
                "class": btn.get_attribute("class"),
                "type": btn.get_attribute("type"),
            })

        log.info(f"Sayfa: {info['title']}")
        log.info(f"Input sayısı: {len(info['inputs'])}")
        log.info(f"Buton sayısı: {len(info['buttons'])}")

        for i, inp in enumerate(info["inputs"]):
            log.info(f"  Input {i}: {inp}")
        for i, btn in enumerate(info["buttons"]):
            log.info(f"  Buton {i}: {btn}")

        return info
