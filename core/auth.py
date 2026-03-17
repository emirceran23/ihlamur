"""
KuveytTürk TradePlus Giriş / Çıkış modülü.
"""

import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from config.settings import TRADEPLUS_URL, TRADEPLUS_TC, TRADEPLUS_PASSWORD, PHONE_VERIFICATION_TIMEOUT, PHONE_VERIFICATION_CHECK_INTERVAL
from utils.logger import get_logger
from utils.helpers import take_screenshot, retry, send_telegram_message

log = get_logger(__name__)


class Auth:
    """TradePlus kimlik doğrulama işlemleri."""

    def __init__(self, driver):
        self.driver = driver
        self.wait = WebDriverWait(driver, 15)
        self.is_logged_in = False

    @retry(max_attempts=2, delay=5.0)
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

        # Login sayfası screenshot'ını Telegram'a gönder
        take_screenshot(self.driver, "🔐 Login sayfası yüklendi")
        send_telegram_message("🔐 TradePlus login sayfası açıldı, giriş başlıyor...")

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
                take_screenshot(self.driver, "❌ TC alanı bulunamadı")
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
                take_screenshot(self.driver, "❌ Şifre alanı bulunamadı")
                raise Exception("Şifre alanı bulunamadı!")

            # ── Adım 3: Giriş butonuna tıkla ─────────────────────
            take_screenshot(self.driver, "📝 TC ve şifre girildi")

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
                take_screenshot(self.driver, "❌ Giriş butonu bulunamadı")
                raise Exception("Giriş butonu bulunamadı!")

            time.sleep(2)

            # ── Adım 4: Telefon doğrulaması bekleme ──────────────
            take_screenshot(self.driver, "📞 Telefon doğrulaması bekleniyor")
            send_telegram_message(
                "📞 <b>TELEFON DOĞRULAMASI BEKLENİYOR!</b>\n\n"
                "Çağrı merkezi seni arayacak.\n"
                "Aramayı cevaplayıp doğrulama yap.\n"
                f"⏱ Maksimum bekleme: {PHONE_VERIFICATION_TIMEOUT} saniye"
            )
            log.info("=" * 60)
            log.info("📞 TELEFON DOĞRULAMASI BEKLENİYOR!")
            log.info("   Çağrı merkezi sizi arayacak.")
            log.info("   Aramayı cevaplayıp doğrulama yapın.")
            log.info(f"   Maksimum bekleme: {PHONE_VERIFICATION_TIMEOUT} saniye")
            log.info("=" * 60)

            if not self._wait_for_phone_verification():
                take_screenshot(self.driver, "❌ Doğrulama zaman aşımı")
                send_telegram_message("❌ Telefon doğrulaması zaman aşımına uğradı! (120s)")
                raise Exception("Telefon doğrulaması zaman aşımına uğradı!")

            # ── Adım 5: Giriş sonrası doğrulama ──────────────────
            time.sleep(3)
            self._verify_login()
            self.is_logged_in = True
            take_screenshot(self.driver, "✅ Giriş başarılı")
            send_telegram_message("✅ TradePlus'a başarıyla giriş yapıldı!")
            log.info("✅ TradePlus'a başarıyla giriş yapıldı!")
            return True

        except Exception as e:
            take_screenshot(self.driver, f"❌ Login hatası: {str(e)[:40]}")
            send_telegram_message(f"❌ TradePlus giriş hatası:\n<code>{e}</code>")
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

    def _wait_for_phone_verification(self) -> bool:
        """
        Telefon doğrulamasının tamamlanmasını bekler.
        
        KuveytTürk çağrı merkezi arar, kullanıcı onaylar.
        Bu sırada bot, sayfanın değişip değişmediğini kontrol eder.
        
        Doğrulama tamamlanınca sayfa otomatik olarak /sayfam/'a yönlendirilir.
        """
        login_url = self.driver.current_url
        log.info(f"Doğrulama öncesi URL: {login_url}")
        
        # Sayfada doğrulama ile ilgili mesaj var mı kontrol et
        take_screenshot(self.driver, "phone_verification_waiting")
        
        # Sayfadaki doğrulama mesajını logla
        try:
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
            # Doğrulama ile ilgili anahtar kelimeler ara
            for keyword in ["doğrulama", "Doğrulama", "aranıyor", "telefon", "Telefon", "onay", "Onay", "çağrı", "Çağrı"]:
                if keyword in body_text:
                    # İlgili kısmı bul ve logla
                    idx = body_text.find(keyword)
                    start = max(0, idx - 50)
                    end = min(len(body_text), idx + 100)
                    log.info(f"📞 Doğrulama mesajı bulundu: ...{body_text[start:end]}...")
                    break
        except Exception:
            pass
        
        elapsed = 0
        while elapsed < PHONE_VERIFICATION_TIMEOUT:
            time.sleep(PHONE_VERIFICATION_CHECK_INTERVAL)
            elapsed += PHONE_VERIFICATION_CHECK_INTERVAL
            
            current_url = self.driver.current_url
            
            # URL değiştiyse doğrulama tamamlanmış demektir
            if current_url != login_url and "sayfam" in current_url:
                log.info(f"✅ Telefon doğrulaması tamamlandı! ({elapsed}s)")
                log.info(f"   Yeni URL: {current_url}")
                return True
            
            # Sayfada başarılı giriş göstergesi var mı
            try:
                # "sayfam" veya dashboard benzeri bir element arayalım
                success_indicators = [
                    (By.XPATH, "//*[contains(text(), 'Portföy')]"),
                    (By.XPATH, "//*[contains(text(), 'Kurlar')]"),
                    (By.XPATH, "//*[contains(text(), 'Hesap')]"),
                    (By.CSS_SELECTOR, "[class*='MuiTab']"),
                ]
                for by, value in success_indicators:
                    try:
                        el = self.driver.find_element(by, value)
                        if el.is_displayed():
                            log.info(f"✅ Dashboard elementi bulundu, giriş başarılı! ({elapsed}s)")
                            return True
                    except Exception:
                        continue
            except Exception:
                pass
            
            # Her 30 saniyede bir durum bilgisi ver (Telegram'a da)
            if elapsed % 30 == 0:
                log.info(f"⏳ Telefon doğrulaması bekleniyor... ({elapsed}/{PHONE_VERIFICATION_TIMEOUT}s)")
                take_screenshot(self.driver, f"⏳ Doğrulama bekleniyor ({elapsed}s)")
                send_telegram_message(f"⏳ Hâlâ bekleniyor... ({elapsed}/{PHONE_VERIFICATION_TIMEOUT}s)\nTelefonu cevapla!")
        
        log.error(f"❌ Telefon doğrulaması {PHONE_VERIFICATION_TIMEOUT}s içinde tamamlanamadı!")
        return False

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
