"""
KuveytTürk TradePlus Giriş / Çıkış modülü.
"""

import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from config.settings import (
    TRADEPLUS_URL, TRADEPLUS_TC, TRADEPLUS_PASSWORD,
    TRADEPLUS_ACCOUNT_NO, TRADEPLUS_PHONE,
    PHONE_VERIFICATION_TIMEOUT, PHONE_VERIFICATION_CHECK_INTERVAL,
)
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

        Form alanları (Bireysel tab):
        1. Müşteri No
        2. Şifre
        3. Kayıtlı Cep Telefonu (90...)
        4. CAPTCHA (görsel kod)
        5. "İleri" butonu
        6. Telefon doğrulaması (çağrı merkezi arar)
        """
        log.info("TradePlus'a giriş yapılıyor...")
        self.driver.get(TRADEPLUS_URL)
        time.sleep(5)

        take_screenshot(self.driver, "🌐 TradePlus ana sayfa")
        send_telegram_message("🌐 TradePlus ana sayfası açıldı...")

        try:
            # ── Adım 0: Sayfayı keşfet ve profil ikonuna tıkla ──
            log.info("Sayfadaki elementler keşfediliyor...")
            self._debug_page_elements()

            log.info("Profil ikonuna tıklanıyor...")
            account_icon = self._find_element(
                possible_selectors=[
                    # Spesifik: SVG id="Component_80_1" içeren buton
                    (By.XPATH, "//button[.//svg[@id='Component_80_1']]"),
                    (By.XPATH, "//button[.//svg[contains(@data-name, 'Component 80')]]"),
                    # jss128 div'ini içeren buton
                    (By.XPATH, "//button[.//div[contains(@class, 'jss128')]]"),
                    # jss127 class'ına sahip buton
                    (By.CSS_SELECTOR, "button.jss127"),
                    # Component_80 SVG'sinin parent butonu
                    (By.CSS_SELECTOR, "#Component_80_1"),
                    (By.XPATH, "//*[@id='Component_80_1']/ancestor::button"),
                ],
                description="Profil/Account ikonu",
                timeout=5,
            )

            if account_icon:
                account_icon.click()
                log.info("Profil ikonuna tıklandı.")
                time.sleep(3)
                
                # Login modal açıldı mı kontrol et
                login_modal_open = False
                try:
                    modal = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.XPATH, 
                            "//*[contains(text(), 'Müşteri No') or contains(text(), 'Bireysel') or contains(text(), 'Kurumsal')]"
                        ))
                    )
                    if modal.is_displayed():
                        login_modal_open = True
                        log.info("✅ Login modal açıldı!")
                except TimeoutException:
                    pass

                if not login_modal_open:
                    take_screenshot(self.driver, "⚠️ Modal açılmadı - yanlış buton")
                    send_telegram_message("⚠️ Tıklandı ama login modal açılmadı! Yanlış butona basılmış olabilir.")
                    raise Exception("Login modal açılmadı! Profil ikonu yanlış tespit edilmiş.")
            else:
                log.warning("Profil ikonu bulunamadı!")
                take_screenshot(self.driver, "⚠️ Profil ikonu bulunamadı")
                send_telegram_message("⚠️ Profil ikonu bulunamadı! Debug bilgileri yukarıda.")
                raise Exception("Profil/Account ikonu bulunamadı!")

            # ── Adım 0.5: "Bireysel" tabına tıkla ─────────────────
            log.info("Bireysel tabına tıklanıyor...")
            bireysel_tab = self._find_element(
                possible_selectors=[
                    (By.XPATH, "//button[text()='Bireysel']"),
                    (By.XPATH, "//span[text()='Bireysel']/.."),
                    (By.XPATH, "//*[contains(@class, 'MuiTab')][contains(text(), 'Bireysel')]"),
                    (By.XPATH, "//button[contains(text(), 'Bireysel')]"),
                ],
                description="Bireysel tabı",
                timeout=5,
            )

            if bireysel_tab:
                bireysel_tab.click()
                log.info("✅ Bireysel tabına tıklandı.")
                time.sleep(2)
            else:
                log.warning("Bireysel tabı bulunamadı, zaten seçili olabilir.")

            take_screenshot(self.driver, "🔐 Bireysel login formu")
            send_telegram_message("🔐 Bireysel login formu açıldı, bilgiler giriliyor...")

            # ── Adım 1: Müşteri No girişi ────────────────────────
            log.info("Müşteri No giriliyor...")
            musteri_input = self._find_element(
                possible_selectors=[
                    # "Müşteri No" label'ına sahip input
                    (By.XPATH, "//label[contains(text(), 'Müşteri')]/following-sibling::div//input"),
                    (By.XPATH, "//label[contains(text(), 'Müşteri No')]/../..//input"),
                    (By.XPATH, "(//input[@type='text' or @type='tel' or @type='number'])[1]"),
                    # MUI form içindeki ilk input
                    (By.CSS_SELECTOR, ".MuiDialog-root input:first-of-type"),
                    (By.CSS_SELECTOR, ".MuiModal-root input:first-of-type"),
                    (By.CSS_SELECTOR, "[role='dialog'] input:first-of-type"),
                ],
                description="Müşteri No alanı",
            )

            if musteri_input:
                musteri_input.clear()
                musteri_input.send_keys(TRADEPLUS_ACCOUNT_NO)
                log.info(f"Müşteri No girildi: {TRADEPLUS_ACCOUNT_NO[:3]}***")
            else:
                take_screenshot(self.driver, "❌ Müşteri No alanı bulunamadı")
                raise Exception("Müşteri No alanı bulunamadı!")

            # ── Adım 2: Şifre girişi ─────────────────────────────
            log.info("Şifre giriliyor...")
            password_input = self._find_element(
                possible_selectors=[
                    (By.CSS_SELECTOR, "[role='dialog'] input[type='password']"),
                    (By.CSS_SELECTOR, ".MuiDialog-root input[type='password']"),
                    (By.CSS_SELECTOR, ".MuiModal-root input[type='password']"),
                    (By.CSS_SELECTOR, "input[type='password']"),
                    (By.XPATH, "//label[contains(text(), 'Şifre')]/../..//input"),
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

            # ── Adım 3: Kayıtlı Cep Telefonu ─────────────────────
            log.info("Cep telefonu giriliyor...")
            phone_input = self._find_element(
                possible_selectors=[
                    (By.XPATH, "//label[contains(text(), 'Telefon')]/../..//input"),
                    (By.XPATH, "//label[contains(text(), 'Cep')]/../..//input"),
                    (By.XPATH, "//label[contains(text(), 'Kayıtlı')]/../..//input"),
                    # "90" değeri olan input (varsayılan değer)
                    (By.XPATH, "//input[@value='90']"),
                    (By.XPATH, "(//input[@type='text' or @type='tel' or @type='number'])[3]"),
                ],
                description="Cep Telefonu alanı",
            )

            if phone_input:
                phone_input.clear()
                phone_input.send_keys(TRADEPLUS_PHONE)
                log.info(f"Cep telefonu girildi: {TRADEPLUS_PHONE[:5]}*****")
            else:
                take_screenshot(self.driver, "❌ Telefon alanı bulunamadı")
                raise Exception("Cep Telefonu alanı bulunamadı!")

            # ── Adım 4: CAPTCHA ───────────────────────────────────
            # CAPTCHA görseli var - bunu Telegram'a gönderip kullanıcıdan alacağız
            take_screenshot(self.driver, "🔑 CAPTCHA - kodu gir")
            send_telegram_message(
                "🔑 <b>CAPTCHA KODU GEREKLİ!</b>\n\n"
                "Yukarıdaki screenshot'taki görsel kodu oku.\n"
                "Kodu Telegram'dan gönder.\n"
                "⏱ 60 saniye bekleniyor..."
            )
            log.info("CAPTCHA çözümü bekleniyor (Telegram'dan)...")

            captcha_code = self._wait_for_captcha_from_telegram()

            if not captcha_code:
                take_screenshot(self.driver, "❌ CAPTCHA zaman aşımı")
                raise Exception("CAPTCHA kodu alınamadı!")

            captcha_input = self._find_element(
                possible_selectors=[
                    (By.XPATH, "//input[contains(@placeholder, 'kod')]"),
                    (By.XPATH, "//input[contains(@placeholder, 'Kod')]"),
                    (By.XPATH, "//input[contains(@placeholder, 'Görsel')]"),
                    (By.XPATH, "//input[contains(@placeholder, 'görseldeki')]"),
                    # Son input alanı (CAPTCHA genelde en sondadır)
                    (By.XPATH, "(//input[@type='text' or @type='tel'])[last()]"),
                    (By.CSS_SELECTOR, "[role='dialog'] input:last-of-type"),
                ],
                description="CAPTCHA input alanı",
            )

            if captcha_input:
                captcha_input.clear()
                captcha_input.send_keys(captcha_code)
                log.info(f"CAPTCHA kodu girildi: {captcha_code}")
            else:
                take_screenshot(self.driver, "❌ CAPTCHA alanı bulunamadı")
                raise Exception("CAPTCHA input alanı bulunamadı!")

            # ── Adım 5: "İleri" butonuna tıkla ───────────────────
            take_screenshot(self.driver, "📝 Form dolduruldu")
            send_telegram_message("📝 Tüm bilgiler girildi, İleri'ye tıklanıyor...")

            ileri_btn = self._find_element(
                possible_selectors=[
                    (By.XPATH, "//button[contains(text(), 'İleri')]"),
                    (By.XPATH, "//button[contains(text(), 'ileri')]"),
                    (By.XPATH, "//span[contains(text(), 'İleri')]/.."),
                    (By.CSS_SELECTOR, "[role='dialog'] button[type='submit']"),
                    (By.CSS_SELECTOR, ".MuiButton-containedPrimary"),
                ],
                description="İleri butonu",
            )

            if ileri_btn:
                ileri_btn.click()
                log.info("İleri butonuna tıklandı.")
            else:
                take_screenshot(self.driver, "❌ İleri butonu bulunamadı")
                raise Exception("İleri butonu bulunamadı!")

            time.sleep(3)
            take_screenshot(self.driver, "📞 İleri tıklandı - sonraki adım")

            # ── Adım 6: Telefon doğrulaması bekleme ──────────────
            send_telegram_message(
                "📞 <b>TELEFON DOĞRULAMASI BEKLENİYOR!</b>\n\n"
                "Çağrı merkezi seni arayacak.\n"
                "Aramayı cevaplayıp doğrulama yap.\n"
                f"⏱ Maksimum bekleme: {PHONE_VERIFICATION_TIMEOUT} saniye"
            )
            log.info("📞 Telefon doğrulaması bekleniyor...")

            if not self._wait_for_phone_verification():
                take_screenshot(self.driver, "❌ Doğrulama zaman aşımı")
                send_telegram_message("❌ Telefon doğrulaması zaman aşımına uğradı!")
                raise Exception("Telefon doğrulaması zaman aşımına uğradı!")

            # ── Adım 7: Giriş sonrası doğrulama ──────────────────
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

    def _debug_page_elements(self):
        """
        Sayfadaki tüm önemli elementleri loglar ve Telegram'a gönderir.
        Profil ikonu gibi elementleri bulmak için kullanılır.
        """
        debug_msg = "🔍 <b>Sayfa Elementleri:</b>\n\n"

        # Tüm butonları listele
        buttons = self.driver.find_elements(By.TAG_NAME, "button")
        debug_msg += f"<b>Butonlar ({len(buttons)}):</b>\n"
        for i, btn in enumerate(buttons):
            try:
                text = btn.text[:30] if btn.text else ""
                cls = btn.get_attribute("class") or ""
                aria = btn.get_attribute("aria-label") or ""
                visible = btn.is_displayed()
                if visible:
                    line = f"[{i}] text='{text}' aria='{aria}' class={cls[:60]}"
                    log.info(f"  Buton {line}")
                    debug_msg += f"<code>{line}</code>\n"
            except Exception:
                pass

        # Tüm SVG ikonlarını listele
        svgs = self.driver.find_elements(By.TAG_NAME, "svg")
        debug_msg += f"\n<b>SVG'ler ({len(svgs)}):</b>\n"
        for i, svg in enumerate(svgs):
            try:
                testid = svg.get_attribute("data-testid") or ""
                cls = svg.get_attribute("class") or ""
                parent_tag = svg.find_element(By.XPATH, "..").tag_name
                parent_cls = svg.find_element(By.XPATH, "..").get_attribute("class") or ""
                if testid or "Icon" in cls:
                    line = f"[{i}] testid='{testid}' class={cls[:40]} parent=<{parent_tag} class={parent_cls[:40]}>"
                    log.info(f"  SVG {line}")
                    debug_msg += f"<code>{line}</code>\n"
            except Exception:
                pass

        # MuiIconButton'ları listele (innerHTML ile)
        icon_btns = self.driver.find_elements(By.CSS_SELECTOR, "[class*='MuiIconButton']")
        debug_msg += f"\n<b>IconButton'lar ({len(icon_btns)}):</b>\n"
        for i, ib in enumerate(icon_btns):
            try:
                cls = ib.get_attribute("class") or ""
                aria = ib.get_attribute("aria-label") or ""
                inner_html = ib.get_attribute("innerHTML") or ""
                # SVG data-testid'ini çıkar
                svg_testid = ""
                try:
                    svg_el = ib.find_element(By.TAG_NAME, "svg")
                    svg_testid = svg_el.get_attribute("data-testid") or ""
                except Exception:
                    pass
                visible = ib.is_displayed()
                if visible:
                    line = f"[{i}] aria='{aria}' svg='{svg_testid}' class={cls[:50]} html={inner_html[:80]}"
                    log.info(f"  IconBtn {line}")
                    debug_msg += f"<code>{line}</code>\n"
            except Exception:
                pass

        # img ve a etiketleri (header'daki)
        imgs = self.driver.find_elements(By.CSS_SELECTOR, "header img, nav img, [class*='header'] img")
        debug_msg += f"\n<b>Header img'leri ({len(imgs)}):</b>\n"
        for i, img in enumerate(imgs):
            try:
                src = img.get_attribute("src") or ""
                alt = img.get_attribute("alt") or ""
                line = f"[{i}] alt='{alt}' src={src[:60]}"
                log.info(f"  Img {line}")
                debug_msg += f"<code>{line}</code>\n"
            except Exception:
                pass

        # Mesajı Telegram'a gönder (çok uzunsa kes)
        if len(debug_msg) > 4000:
            debug_msg = debug_msg[:4000] + "\n...(kesildi)"
        send_telegram_message(debug_msg)

    def _find_element(self, possible_selectors: list, description: str, timeout: int = 5):
        """
        Birden fazla selector ile element bulmayı dener.
        Kısa timeout ile hızlıca deneyip geçer.
        """
        for by, value in possible_selectors:
            try:
                element = WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((by, value))
                )
                log.info(f"✅ {description} bulundu: {by}={value}")
                return element
            except TimeoutException:
                log.debug(f"  ❌ {description}: {by}={value} bulunamadı")
                continue
        log.warning(f"{description} hiçbir selector ile bulunamadı!")
        return None

    def _wait_for_captcha_from_telegram(self, timeout: int = 90) -> str | None:
        """
        Telegram'dan CAPTCHA kodunu bekler.
        
        Bot, Telegram'daki son mesajı kontrol eder.
        Kullanıcı CAPTCHA kodunu Telegram'a yazınca bot okur.
        """
        import requests
        from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
        
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            log.error("Telegram bilgileri eksik! CAPTCHA alınamaz.")
            return None
        
        # Mevcut son mesaj ID'sini al (bu mesajdan sonrakileri okuyacağız)
        last_update_id = self._get_last_telegram_update_id()
        
        log.info(f"CAPTCHA kodu bekleniyor (Telegram'dan, {timeout}s)...")
        
        elapsed = 0
        check_interval = 3
        while elapsed < timeout:
            time.sleep(check_interval)
            elapsed += check_interval
            
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
                params = {"offset": last_update_id + 1 if last_update_id else -1, "timeout": 1}
                resp = requests.get(url, params=params, timeout=10)
                data = resp.json()
                
                if data.get("ok") and data.get("result"):
                    for update in data["result"]:
                        msg = update.get("message", {})
                        chat_id = str(msg.get("chat", {}).get("id", ""))
                        text = msg.get("text", "").strip()
                        
                        # Doğru chat'ten gelen mesaj mı?
                        if chat_id == str(TELEGRAM_CHAT_ID) and text:
                            # CAPTCHA kodu genelde 5-6 karakter alfanumerik
                            if 3 <= len(text) <= 10:
                                log.info(f"✅ CAPTCHA kodu Telegram'dan alındı: {text}")
                                send_telegram_message(f"✅ CAPTCHA kodu alındı: <b>{text}</b>")
                                return text
            except Exception as e:
                log.debug(f"Telegram kontrol hatası: {e}")
            
            if elapsed % 15 == 0:
                log.info(f"⏳ CAPTCHA bekleniyor... ({elapsed}/{timeout}s)")
        
        log.error(f"CAPTCHA kodu {timeout}s içinde alınamadı!")
        return None
    
    def _get_last_telegram_update_id(self) -> int:
        """Telegram'daki son update ID'sini alır."""
        import requests
        from config.settings import TELEGRAM_BOT_TOKEN
        
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
            params = {"offset": -1, "limit": 1}
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            if data.get("ok") and data.get("result"):
                return data["result"][-1].get("update_id", 0)
        except Exception:
            pass
        return 0

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
