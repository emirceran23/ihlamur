"""
KuveytTürk İnternet Şubesi — Giriş / Çıkış modülü.

Akış:
  1. isube.kuveytturk.com.tr/Login/InitialLogin aç
  2. "Önemli Bilgilendirme" popup → TAMAM tıkla
  3. Müşteri No / T.C. Kimlik No gir
  4. Şifre gir
  5. Kayıtlı Cep Telefonu gir
  6. CAPTCHA → Telegram'a gönder, kullanıcıdan kodu al
  7. Doğrulama Resmi gir
  8. DEVAM tıkla
  9. Mobil onay bekle (telefon onay + bayrak seçimi)
 10. Giriş doğrula
"""

import time
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from config.settings import (
    KUVEYTTURK_URL, KUVEYTTURK_TC, KUVEYTTURK_PASSWORD,
    KUVEYTTURK_PHONE,
    PHONE_VERIFICATION_TIMEOUT, PHONE_VERIFICATION_CHECK_INTERVAL,
)
from utils.logger import get_logger
from utils.helpers import take_screenshot, retry, send_telegram_message

log = get_logger(__name__)


class Auth:
    """KuveytTürk İnternet Şubesi kimlik doğrulama."""

    def __init__(self, driver):
        self.driver = driver
        self.wait = WebDriverWait(driver, 15)
        self.is_logged_in = False
        self.session_manager = None  # main.py'den set edilir

    # ──────────────────────────────────────────────────────────
    #  LOGIN
    # ──────────────────────────────────────────────────────────
    @retry(max_attempts=2, delay=5.0)
    def login(self) -> bool:
        """KuveytTürk İnternet Şubesi'ne giriş yapar."""
        log.info("KuveytTürk İnternet Şubesi'ne giriş yapılıyor...")
        self.driver.get(KUVEYTTURK_URL)
        time.sleep(4)

        take_screenshot(self.driver, "🌐 İnternet Şubesi açıldı")
        send_telegram_message("🌐 KuveytTürk İnternet Şubesi açıldı...")

        try:
            # ── Adım 0: "Önemli Bilgilendirme" popup — TAMAM ─────
            log.info("Popup kontrol ediliyor...")
            try:
                tamam_btn = WebDriverWait(self.driver, 8).until(
                    EC.element_to_be_clickable((
                        By.XPATH,
                        "//button[contains(text(), 'TAMAM')] | "
                        "//input[@value='TAMAM'] | "
                        "//a[contains(text(), 'TAMAM')]"
                    ))
                )
                tamam_btn.click()
                log.info("✅ Popup kapatıldı (TAMAM)")
                time.sleep(2)
                take_screenshot(self.driver, "✅ Popup kapatıldı")
            except TimeoutException:
                log.info("Popup yok veya zaten kapalı, devam ediliyor...")

            # Popup kapandıktan sonra BİREYSEL sekmesine tıkla (zaten aktif olabilir)
            try:
                bireysel = self.driver.find_element(
                    By.XPATH, "//a[contains(text(), 'BİREYSEL') or contains(text(), 'Bireysel')]"
                )
                bireysel.click()
                time.sleep(1)
                log.info("✅ Bireysel sekmesi tıklandı")
            except Exception:
                log.info("Bireysel sekmesi zaten aktif veya bulunamadı")

            # ── Adım 1: Müşteri No / T.C. Kimlik No ──────────────
            # NOT: Bu alan <input> değil, <div contenteditable="true" id="CustomerNumberDisplay">
            log.info("Müşteri No giriliyor...")
            musteri_div = self._find_element(
                possible_selectors=[
                    (By.ID, "CustomerNumberDisplay"),
                    (By.CSS_SELECTOR, "div#CustomerNumberDisplay"),
                ],
                description="Müşteri No (contenteditable div)",
                timeout=10,
            )

            if musteri_div:
                # KuveytTürk güvenlik: charDiff > 1 ise alert veriyor.
                # Her karakteri tek tek insertText ile yazıp, sonra blur tetikliyoruz.
                # blur event'i updateCustomerNumberMapping() çağırarak IntUserName'i dolduruyor.
                self.driver.execute_script("""
                    var el = arguments[0];
                    var text = arguments[1];

                    el.focus();
                    el.click();

                    // Mevcut içeriği temizle
                    document.execCommand('selectAll', false, null);
                    document.execCommand('delete', false, null);

                    // Her karakteri tek tek yaz (charDiff > 1 korumasını bypass)
                    for (var i = 0; i < text.length; i++) {
                        document.execCommand('insertText', false, text[i]);
                    }

                    // blur tetikle — updateCustomerNumberMapping() çalışsın
                    el.dispatchEvent(new Event('blur', { bubbles: true }));
                """, musteri_div, KUVEYTTURK_TC)
                time.sleep(0.5)

                log.info(f"Müşteri No girildi: {KUVEYTTURK_TC[:3]}***")
                take_screenshot(self.driver, "✅ Müşteri No girildi")
            else:
                take_screenshot(self.driver, "❌ Müşteri No alanı bulunamadı")
                raise Exception("Müşteri No alanı bulunamadı!")

            # ── Adım 2: Şifre (sanal klavye ile) ─────────────────
            log.info("Şifre giriliyor (sanal klavye)...")
            self._type_password_virtual_keyboard(KUVEYTTURK_PASSWORD)
            take_screenshot(self.driver, "✅ Şifre girildi")

            # ── Adım 3: Kayıtlı Cep Telefonu ─────────────────────
            log.info("Cep telefonu giriliyor...")
            phone_input = self._find_element(
                possible_selectors=[
                    (By.ID, "GsmNumber"),
                    (By.NAME, "GsmNumber"),
                ],
                description="Cep Telefonu",
            )

            if phone_input:
                self._js_input(phone_input, KUVEYTTURK_PHONE)
                log.info(f"Telefon girildi: {KUVEYTTURK_PHONE[:3]}***")
                take_screenshot(self.driver, "✅ Telefon girildi")
            else:
                take_screenshot(self.driver, "❌ Telefon alanı bulunamadı")
                raise Exception("Telefon alanı bulunamadı!")

            # ── Adım 4: CAPTCHA ───────────────────────────────────
            log.info("CAPTCHA çözülecek...")
            take_screenshot(self.driver, "🔐 CAPTCHA — kodu girin")
            send_telegram_message(
                "🔐 <b>CAPTCHA kodu gerekli!</b>\n"
                "Yukarıdaki görseldeki kodu mesaj olarak gönderin."
            )

            captcha_code = self._wait_for_captcha_from_telegram(timeout=120)
            if not captcha_code:
                raise Exception("CAPTCHA kodu alınamadı (timeout)!")

            captcha_input = self._find_element(
                possible_selectors=[
                    (By.ID, "Captcha"),
                    (By.NAME, "Captcha"),
                ],
                description="CAPTCHA / Doğrulama Resmi",
            )

            if captcha_input:
                self._js_input(captcha_input, captcha_code)
                log.info(f"CAPTCHA girildi: {captcha_code}")
                take_screenshot(self.driver, "✅ CAPTCHA girildi")
            else:
                take_screenshot(self.driver, "❌ CAPTCHA alanı bulunamadı")
                raise Exception("CAPTCHA alanı bulunamadı!")

            # ── Adım 5: DEVAM butonu ─────────────────────────────
            log.info("DEVAM butonuna tıklanıyor...")
            devam_btn = self._find_element(
                possible_selectors=[
                    (By.ID, "btnSubmit"),
                    (By.CSS_SELECTOR, "input#btnSubmit"),
                    (By.XPATH, "//input[@id='btnSubmit']"),
                ],
                description="DEVAM butonu",
            )

            if devam_btn:
                self.driver.execute_script("arguments[0].click();", devam_btn)
                log.info("✅ DEVAM tıklandı.")
                time.sleep(3)
                take_screenshot(self.driver, "✅ DEVAM sonrası")
            else:
                take_screenshot(self.driver, "❌ DEVAM butonu bulunamadı")
                raise Exception("DEVAM butonu bulunamadı!")

            # ── Adım 6: Güvenlik Resmi Doğrulama — GİRİŞ ──────────
            # DEVAM sonrası "Güvenlik resminizi doğrulayın" sayfası açılır.
            # Türk Bayrağı gösterilir, kullanıcı doğrulayıp GİRİŞ'e basar.
            log.info("Güvenlik resmi doğrulama sayfası kontrol ediliyor...")
            take_screenshot(self.driver, "🔐 Güvenlik resmi doğrulama")
            send_telegram_message(
                "🔐 <b>Güvenlik Resmi Doğrulama</b>\n"
                "Güvenlik resminizi (Türk Bayrağı) kontrol edin.\n"
                "Bot otomatik olarak GİRİŞ butonuna tıklayacak..."
            )

            giris_btn = self._find_element(
                possible_selectors=[
                    (By.XPATH, "//input[@value='GİRİŞ']"),
                    (By.XPATH, "//button[contains(text(), 'GİRİŞ')]"),
                    (By.XPATH, "//input[contains(@value, 'RİŞ')]"),
                    (By.CSS_SELECTOR, "input[type='submit']"),
                    (By.ID, "btnLogin"),
                    (By.ID, "LoginButton"),
                ],
                description="GİRİŞ butonu",
                timeout=10,
            )

            if giris_btn:
                self.driver.execute_script("arguments[0].click();", giris_btn)
                log.info("✅ GİRİŞ tıklandı.")
                time.sleep(3)
                take_screenshot(self.driver, "✅ GİRİŞ sonrası")
            else:
                log.warning("GİRİŞ butonu bulunamadı, sayfa zaten ilerlemiş olabilir.")

            # ── Adım 7: Mobil onay bekle ──────────────────────────
            log.info("📱 Mobil onay bekleniyor...")
            send_telegram_message(
                "📱 <b>Mobil Onay Gerekli!</b>\n"
                "Telefonunuza gelen onay bildirimini onaylayın.\n"
                f"⏱ Bekleme süresi: {PHONE_VERIFICATION_TIMEOUT} saniye"
            )
            take_screenshot(self.driver, "📱 Mobil onay bekleniyor")

            if self._wait_for_mobile_verification():
                log.info("✅ Mobil onay başarılı!")
                take_screenshot(self.driver, "✅ Giriş başarılı")
                send_telegram_message("✅ KuveytTürk İnternet Şubesi girişi başarılı!")
                self.is_logged_in = True

                # Cookie'leri kaydet — session yöneticisi varsa
                if self.session_manager:
                    self.session_manager.save_cookies()
                    log.info("Cookie'ler kaydedildi (yeni oturum).")

                return True
            else:
                take_screenshot(self.driver, "❌ Mobil onay timeout")
                raise Exception("Mobil onay zaman aşımına uğradı!")

        except Exception as e:
            log.error(f"Login hatası: {e}")
            take_screenshot(self.driver, "❌ Login hatası")
            raise

    # ──────────────────────────────────────────────────────────
    #  LOGOUT
    # ──────────────────────────────────────────────────────────
    def logout(self):
        """İnternet Şubesi'nden çıkış yapar."""
        try:
            log.info("Çıkış yapılıyor...")
            logout_el = self._find_element(
                possible_selectors=[
                    (By.XPATH, "//a[contains(text(), 'Çıkış')]"),
                    (By.XPATH, "//a[contains(text(), 'Güvenli Çıkış')]"),
                    (By.XPATH, "//a[contains(@href, 'Logout')]"),
                    (By.CSS_SELECTOR, "a[href*='Logout']"),
                ],
                description="Çıkış butonu",
            )
            if logout_el:
                logout_el.click()
                log.info("✅ Çıkış yapıldı.")
                self.is_logged_in = False
            else:
                log.warning("Çıkış butonu bulunamadı.")
        except Exception as e:
            log.error(f"Çıkış hatası: {e}")

    # ──────────────────────────────────────────────────────────
    #  YARDIMCI METODLAR
    # ──────────────────────────────────────────────────────────
    def _js_input(self, element, text: str):
        """
        JavaScript ile input alanına değer girer.
        element not interactable hatasını bypass eder.
        """
        self.driver.execute_script("""
            var el = arguments[0];
            var text = arguments[1];
            el.value = '';
            el.focus();
            el.value = text;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        """, element, text)
        time.sleep(0.3)

    def _type_password_virtual_keyboard(self, password: str):
        """
        Sanal klavye butonlarına tıklayarak şifre girer.
        KuveytTürk sanal klavyesi: butonlar id=M0..M43 ile sıralı,
        her butonun text'i bir karakter. Karakter-buton eşleştirmesi
        yapılarak şifrenin her karakteri tek tek tıklanır.
        """
        # Önce Password alanına tıkla — sanal klavyeyi aktifleştir
        try:
            pw_field = self.driver.find_element(By.ID, "Password")
            pw_field.click()
            time.sleep(0.5)
        except Exception:
            pass

        # Sanal klavye butonlarını topla: text → element mapping
        keyboard_buttons = {}
        for i in range(50):  # M0 ... M49 arası tara
            try:
                btn = self.driver.find_element(By.ID, f"M{i}")
                char = btn.text.strip()
                if char:
                    keyboard_buttons[char.lower()] = btn
            except Exception:
                continue

        log.info(f"Sanal klavyede {len(keyboard_buttons)} tuş bulundu: {list(keyboard_buttons.keys())}")

        if not keyboard_buttons:
            # Sanal klavye bulunamadı — direkt send_keys dene
            log.warning("Sanal klavye bulunamadı, send_keys deneniyor...")
            pw_field = self.driver.find_element(By.ID, "Password")
            pw_field.send_keys(password)
            return

        # Şifrenin her karakteri için ilgili butona tıkla
        for ch in password:
            ch_lower = ch.lower()
            if ch_lower in keyboard_buttons:
                keyboard_buttons[ch_lower].click()
                time.sleep(0.15)
                log.debug(f"Sanal klavye: '{ch_lower}' tıklandı")
            else:
                log.warning(f"Sanal klavyede '{ch}' bulunamadı! Mevcut tuşlar: {list(keyboard_buttons.keys())}")
                raise Exception(f"Sanal klavyede '{ch}' karakteri yok!")

        log.info(f"Şifre sanal klavye ile girildi ({len(password)} karakter)")

    def _find_element(self, possible_selectors: list, description: str, timeout: int = 5):
        """Birden fazla selector ile element bulmayı dener."""
        for by, value in possible_selectors:
            try:
                element = WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((by, value))
                )
                log.info(f"✅ {description} bulundu: {by}={value}")
                return element
            except TimeoutException:
                continue
        log.warning(f"⚠️ {description} bulunamadı! Denenen selector'lar: {possible_selectors}")
        return None

    def _wait_for_captcha_from_telegram(self, timeout: int = 120) -> str | None:
        """Telegram'dan CAPTCHA kodunu bekler."""
        import requests
        from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

        log.info(f"Telegram'dan CAPTCHA kodu bekleniyor (max {timeout}s)...")

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
        try:
            resp = requests.get(url, params={"offset": -1, "limit": 1}, timeout=10)
            data = resp.json()
            last_update_id = 0
            if data.get("result"):
                last_update_id = data["result"][-1]["update_id"]
        except Exception:
            last_update_id = 0

        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                resp = requests.get(
                    url,
                    params={"offset": last_update_id + 1, "timeout": 5},
                    timeout=15,
                )
                data = resp.json()
                for update in data.get("result", []):
                    last_update_id = update["update_id"]
                    msg = update.get("message", {})
                    chat_id = str(msg.get("chat", {}).get("id", ""))
                    text = msg.get("text", "").strip()

                    if chat_id == str(TELEGRAM_CHAT_ID) and text:
                        # '/' ile başlayan mesajlar komut — CAPTCHA değil!
                        if text.startswith("/"):
                            log.debug(f"Komut mesajı atlandı (CAPTCHA değil): {text}")
                            continue
                        log.info(f"CAPTCHA kodu alındı: {text}")
                        send_telegram_message(f"✅ CAPTCHA kodu alındı: <b>{text}</b>")
                        return text
            except Exception as e:
                log.warning(f"Telegram polling hatası: {e}")

            time.sleep(2)

        log.error("CAPTCHA kodu alınamadı — zaman aşımı!")
        return None

    def _wait_for_mobile_verification(self) -> bool:
        """
        Mobil onay + görsel seçimi sonrası sayfanın değişmesini bekler.
        Login sayfasından çıkılırsa → onay başarılıdır.
        """
        log.info(f"Mobil onay bekleniyor (max {PHONE_VERIFICATION_TIMEOUT}s)...")
        start_time = time.time()
        login_url = self.driver.current_url

        while time.time() - start_time < PHONE_VERIFICATION_TIMEOUT:
            current_url = self.driver.current_url

            # URL login sayfasından farklılaştıysa → giriş başarılı
            if "Login" not in current_url and current_url != login_url:
                log.info(f"✅ URL değişti: {current_url}")
                return True

            # Sayfa içeriğinde dashboard elementleri
            # NOT: "Hoş Geldiniz" login sayfasında da var — kullanma!
            try:
                page_text = self.driver.find_element(By.TAG_NAME, "body").text
                if any(kw in page_text for kw in [
                    "Hesaplarım", "Hesap Özeti", "Bakiye",
                    "Havale", "EFT", "Döviz", "Yatırım",
                ]):
                    log.info("✅ Dashboard içeriği algılandı!")
                    return True
            except Exception:
                pass

            elapsed = int(time.time() - start_time)
            if elapsed % 15 == 0 and elapsed > 0:
                take_screenshot(self.driver, f"⏳ Onay bekleniyor ({elapsed}s)")

            time.sleep(PHONE_VERIFICATION_CHECK_INTERVAL)

        return False

    def explore_page(self):
        """
        Sayfadaki form elementlerini keşfeder ve Telegram'a gönderir.
        Popup kapatır, iframe kontrol eder, tüm input/button'ları listeler.
        """
        log.info("Sayfa yapısı keşfediliyor...")

        # Popup kapat
        try:
            tamam_btn = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((
                    By.XPATH,
                    "//button[contains(text(), 'TAMAM')] | "
                    "//input[@value='TAMAM'] | "
                    "//a[contains(text(), 'TAMAM')]"
                ))
            )
            tamam_btn.click()
            log.info("✅ Popup kapatıldı")
            time.sleep(1)
        except TimeoutException:
            log.info("Popup yok")

        take_screenshot(self.driver, "🔍 Popup sonrası sayfa")

        debug_msg = "🔍 <b>Sayfa Yapısı (İnternet Şubesi)</b>\n\n"
        debug_msg += f"URL: {self.driver.current_url}\n"
        debug_msg += f"Title: {self.driver.title}\n\n"

        # iframe var mı kontrol et
        iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
        debug_msg += f"<b>🖼 iframe sayısı: {len(iframes)}</b>\n"
        for i, iframe in enumerate(iframes):
            ifr_id = iframe.get_attribute("id") or "-"
            ifr_name = iframe.get_attribute("name") or "-"
            ifr_src = (iframe.get_attribute("src") or "-")[:80]
            debug_msg += f"  {i+1}. id={ifr_id} name={ifr_name} src={ifr_src}\n"

        # Ana sayfadaki input'lar — görünürlük bilgisi ile
        inputs = self.driver.find_elements(By.TAG_NAME, "input")
        debug_msg += f"\n<b>📝 Ana sayfa Input'lar ({len(inputs)}):</b>\n"
        for i, inp in enumerate(inputs[:20]):
            inp_id = inp.get_attribute("id") or "-"
            inp_name = inp.get_attribute("name") or "-"
            inp_type = inp.get_attribute("type") or "-"
            inp_value = (inp.get_attribute("value") or "-")[:20]
            is_displayed = inp.is_displayed()
            size = inp.size
            debug_msg += (
                f"  {i+1}. id={inp_id} name={inp_name} type={inp_type} "
                f"val={inp_value} visible={is_displayed} size={size['width']}x{size['height']}\n"
            )

        # iframe'lerin içine gir ve kontrol et
        for i, iframe in enumerate(iframes):
            try:
                self.driver.switch_to.frame(iframe)
                iframe_inputs = self.driver.find_elements(By.TAG_NAME, "input")
                ifr_id = iframe.get_attribute("id") or iframe.get_attribute("name") or str(i)
                debug_msg += f"\n<b>📝 iframe[{ifr_id}] Input'lar ({len(iframe_inputs)}):</b>\n"
                for j, inp in enumerate(iframe_inputs[:15]):
                    inp_id = inp.get_attribute("id") or "-"
                    inp_name = inp.get_attribute("name") or "-"
                    inp_type = inp.get_attribute("type") or "-"
                    inp_value = (inp.get_attribute("value") or "-")[:20]
                    debug_msg += f"  {j+1}. id={inp_id} name={inp_name} type={inp_type} val={inp_value}\n"
                self.driver.switch_to.default_content()
            except Exception as e:
                debug_msg += f"\n  ⚠️ iframe[{i}] erişim hatası: {e}\n"
                self.driver.switch_to.default_content()

        # Butonlar
        buttons = self.driver.find_elements(By.TAG_NAME, "button")
        buttons += self.driver.find_elements(By.CSS_SELECTOR, "input[type='submit']")
        buttons += self.driver.find_elements(By.CSS_SELECTOR, "input[type='button']")
        debug_msg += f"\n<b>🔘 Butonlar ({len(buttons)}):</b>\n"
        for i, btn in enumerate(buttons[:10]):
            btn_id = btn.get_attribute("id") or "-"
            btn_text = btn.text or btn.get_attribute("value") or "-"
            btn_type = btn.get_attribute("type") or "-"
            debug_msg += f"  {i+1}. id={btn_id} text={btn_text} type={btn_type}\n"

        # Tab / sekme linkleri
        links = self.driver.find_elements(By.TAG_NAME, "a")
        tab_links = [l for l in links if any(kw in (l.text or "").upper() for kw in ["BİREYSEL", "KURUMSAL", "BIREYSEL"])]
        debug_msg += f"\n<b>🔗 Tab linkleri ({len(tab_links)}):</b>\n"
        for i, link in enumerate(tab_links):
            link_text = link.text or "-"
            link_href = (link.get_attribute("href") or "-")[:60]
            link_class = (link.get_attribute("class") or "-")[:40]
            debug_msg += f"  {i+1}. text={link_text} href={link_href} class={link_class}\n"

        if len(debug_msg) > 4000:
            debug_msg = debug_msg[:4000] + "\n...(kesildi)"
        send_telegram_message(debug_msg)

        # Müşteri No etrafındaki HTML'i gönder (detaylı debug)
        try:
            musteri_html = self.driver.execute_script("""
                // "Müşteri" içeren td/label/div bul
                var all = document.querySelectorAll('td, label, div, span');
                var results = [];
                for (var i = 0; i < all.length; i++) {
                    var txt = all[i].textContent.trim();
                    if (txt.indexOf('Müşteri') !== -1 || txt.indexOf('T.C.') !== -1 || txt.indexOf('Kimlik') !== -1) {
                        var parent = all[i].parentElement;
                        if (parent) {
                            results.push({
                                tag: all[i].tagName,
                                text: txt.substring(0, 50),
                                parentHTML: parent.innerHTML.substring(0, 500)
                            });
                        }
                    }
                }
                return JSON.stringify(results.slice(0, 3));
            """)
            send_telegram_message(f"🔍 <b>Müşteri No HTML:</b>\n<pre>{musteri_html[:3500]}</pre>")
        except Exception as e:
            send_telegram_message(f"⚠️ Müşteri HTML alınamadı: {e}")

        take_screenshot(self.driver, "🔍 Sayfa keşfi")
        return debug_msg