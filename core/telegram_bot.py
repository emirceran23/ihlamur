"""
İhlamur — Telegram Komut Botu.

Telegram üzerinden bot komutlarıyla sistemi kontrol eder:
  /login      — Oturum aç (önce cookie dener, yoksa tam giriş)
  /relogin    — Cookie'leri sil, sıfırdan giriş yap
  /logout     — Oturumu kapat
  /status     — Oturum durumu
  /screenshot — Anlık ekran görüntüsü
  /explore    — İnteraktif sayfa keşfi (uzaktan kumanda modu)
  /cancel     — Botu durdur (python process'i kapat)
  /help       — Komut listesi

  Explore modundayken (/ olmadan):
    tıkla #elementId         — ID ile tıkla
    tıkla .className         — CSS class ile tıkla
    tıkla //xpath/ifade      — XPath ile tıkla
    tıkla "görünen metin"    — Link text ile tıkla
    yaz #elementId metin     — Elemente text yaz
    git https://url          — URL'ye git
    scroll aşağı / yukarı    — Scroll
    bekle 5                  — N saniye bekle
    js kod                   — JavaScript çalıştır
    scan                     — Sayfayı tekrar tara
    bitti                    — Explore modundan çık

Tasarım kararları (loop'a girmemek için):
  • Tek bir polling thread'i var — komutları okur, handler'a yönlendirir.
  • Her handler kendi thread'inde çalışır ama bir Lock ile korunur:
    aynı anda 2 login/logout çalışamaz.
  • '/' ile başlayan mesajlar CAPTCHA polling'ine GİTMEZ.
  • Explore modu aktifken '/' ile başlamayan mesajlar explore handler'a gider,
    CAPTCHA polling'ine GİTMEZ. Explore kapalıyken normal davranış.
"""

import os
import signal
import threading
import time
import requests

from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    NoSuchElementException,
    ElementNotInteractableException,
)

from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from utils.logger import get_logger
from utils.helpers import send_telegram_message, take_screenshot

log = get_logger(__name__)

# ── Aynı anda tek ağır işlem koruması ─────────────────────
_action_lock = threading.Lock()
_action_name: str = ""


class TelegramBot:
    """
    Telegram long-polling ile komut dinleyen bot.
    Browser/Auth/Session nesneleri dışarıdan enjekte edilir.
    """

    def __init__(self, auth, session, driver):
        self.auth = auth
        self.session = session
        self.driver = driver

        self._polling_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_update_id: int = 0

        # Explore modu
        self._explore_active = False

    # ──────────────────────────────────────────────────────────
    #  BAŞLAT / DURDUR
    # ──────────────────────────────────────────────────────────
    def start(self):
        if self._polling_thread and self._polling_thread.is_alive():
            log.warning("Telegram bot zaten çalışıyor.")
            return

        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            log.error("TELEGRAM_BOT_TOKEN veya TELEGRAM_CHAT_ID eksik!")
            return

        self._stop_event.clear()
        self._flush_pending_updates()

        self._polling_thread = threading.Thread(
            target=self._polling_loop, daemon=True, name="telegram-bot"
        )
        self._polling_thread.start()
        log.info("🤖 Telegram komut botu başlatıldı.")

    def stop(self):
        if self._polling_thread and self._polling_thread.is_alive():
            self._stop_event.set()
            self._polling_thread.join(timeout=15)
        self._polling_thread = None
        log.info("🤖 Telegram komut botu durduruldu.")

    # ──────────────────────────────────────────────────────────
    #  POLLING
    # ──────────────────────────────────────────────────────────
    def _flush_pending_updates(self):
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
            resp = requests.get(url, params={"offset": -1, "limit": 1}, timeout=10)
            data = resp.json()
            if data.get("result"):
                self._last_update_id = data["result"][-1]["update_id"]
                log.info(f"Telegram offset: {self._last_update_id}")
        except Exception as e:
            log.warning(f"Telegram flush hatası: {e}")

    def _polling_loop(self):
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"

        while not self._stop_event.is_set():
            try:
                resp = requests.get(
                    url,
                    params={
                        "offset": self._last_update_id + 1,
                        "timeout": 10,
                        "allowed_updates": '["message"]',
                    },
                    timeout=20,
                )
                data = resp.json()

                for update in data.get("result", []):
                    self._last_update_id = update["update_id"]
                    self._handle_update(update)

            except requests.exceptions.Timeout:
                continue
            except Exception as e:
                log.error(f"Telegram polling hatası: {e}")
                self._stop_event.wait(5)

    def _handle_update(self, update: dict):
        msg = update.get("message", {})
        chat_id = str(msg.get("chat", {}).get("id", ""))
        text = (msg.get("text") or "").strip()

        if chat_id != str(TELEGRAM_CHAT_ID):
            return
        if not text:
            return

        # ── Explore aktifken: '/' olmayan mesajlar → explore handler
        if self._explore_active and not text.startswith("/"):
            threading.Thread(
                target=self._explore_handle_message,
                args=(text,),
                daemon=True,
                name="explore-msg",
            ).start()
            return

        # Komut değilse atla (CAPTCHA polling'ine bırak)
        if not text.startswith("/"):
            return

        command = text.split()[0].lower()
        if "@" in command:
            command = command.split("@")[0]

        log.info(f"Telegram komutu: {command}")

        # Komut haritası
        handlers = {
            "/login": self._cmd_login,
            "/relogin": self._cmd_relogin,
            "/logout": self._cmd_logout,
            "/status": self._cmd_status,
            "/screenshot": self._cmd_screenshot,
            "/ss": self._cmd_screenshot,
            "/explore": self._cmd_explore,
            "/cancel": self._cmd_cancel,
            "/help": self._cmd_help,
            "/start": self._cmd_help,
        }

        handler = handlers.get(command)
        if not handler:
            send_telegram_message(
                f"❓ Bilinmeyen komut: <code>{command}</code>\n/help yazın."
            )
            return

        # Lock gerektirmeyen komutlar
        no_lock = ("/status", "/screenshot", "/ss", "/help", "/start", "/cancel")
        if command in no_lock:
            threading.Thread(
                target=handler, daemon=True, name=f"cmd-{command}"
            ).start()
        else:
            threading.Thread(
                target=self._run_with_lock,
                args=(command, handler),
                daemon=True,
                name=f"cmd-{command}",
            ).start()

    # ──────────────────────────────────────────────────────────
    #  LOCK MEKANİZMASI
    # ──────────────────────────────────────────────────────────
    def _run_with_lock(self, command: str, handler):
        global _action_name

        acquired = _action_lock.acquire(blocking=False)
        if not acquired:
            send_telegram_message(
                f"⏳ <b>Başka bir işlem devam ediyor:</b> {_action_name}\n"
                f"Lütfen bitmesini bekleyin."
            )
            log.warning(f"Komut reddedildi ({command}): {_action_name} devam ediyor.")
            return

        try:
            _action_name = command
            handler()
        except Exception as e:
            log.error(f"Komut hatası ({command}): {e}")
            send_telegram_message(f"❌ <b>Komut hatası ({command}):</b>\n{e}")
        finally:
            _action_name = ""
            _action_lock.release()

    # ──────────────────────────────────────────────────────────
    #  KOMUT HANDLER'LARI — OTURUM
    # ──────────────────────────────────────────────────────────
    def _cmd_login(self):
        send_telegram_message("🔑 <b>Giriş başlatılıyor...</b>\nÖnce cookie ile denenecek.")

        if self.session.try_restore_session():
            self.auth.is_logged_in = True
            send_telegram_message("✅ <b>Oturum cookie ile geri yüklendi!</b>")
            return

        send_telegram_message("🔐 Cookie geçersiz, tam giriş yapılıyor...")
        self.auth.login()

        if self.auth.is_logged_in:
            send_telegram_message("✅ <b>Giriş başarılı!</b>")
        else:
            send_telegram_message("❌ <b>Giriş başarısız!</b>")

    def _cmd_relogin(self):
        send_telegram_message("🔄 <b>Yeniden giriş başlatılıyor...</b>")

        try:
            if self.auth.is_logged_in:
                self.auth.logout()
        except Exception:
            pass

        self.session._delete_cookie_file()
        self.auth.is_logged_in = False

        send_telegram_message("🔐 Sıfırdan giriş yapılıyor...")
        self.auth.login()

        if self.auth.is_logged_in:
            send_telegram_message("✅ <b>Yeniden giriş başarılı!</b>")
        else:
            send_telegram_message("❌ <b>Yeniden giriş başarısız!</b>")

    def _cmd_logout(self):
        if not self.auth.is_logged_in:
            send_telegram_message("ℹ️ Zaten giriş yapılmamış.")
            return

        send_telegram_message("🔓 <b>Çıkış yapılıyor...</b>")
        self.auth.logout()
        self.session._delete_cookie_file()
        send_telegram_message("✅ <b>Çıkış yapıldı.</b> Cookie'ler silindi.")

    # ──────────────────────────────────────────────────────────
    #  KOMUT HANDLER'LARI — İZLEME
    # ──────────────────────────────────────────────────────────
    def _cmd_status(self):
        info = self.session.session_info()
        logged_in = self.auth.is_logged_in
        status_emoji = "🟢" if logged_in else "🔴"

        msg = (
            f"{status_emoji} <b>İhlamur Durum</b>\n\n"
            f"Oturum: {'Açık' if logged_in else 'Kapalı'}\n"
            f"Cookie: {'✅ Var' if info['cookie_file_exists'] else '❌ Yok'}\n"
        )

        if info["cookie_file_exists"]:
            msg += (
                f"Cookie yaşı: {info['session_age_minutes']:.1f} dk\n"
                f"Max yaş: {info['max_age_seconds'] / 60:.0f} dk\n"
                f"Son kayıt: {info['saved_at']}\n"
            )

        msg += (
            f"Keep-alive: {'✅ Aktif' if info['keepalive_running'] else '❌ Pasif'}\n"
            f"Explore: {'🔍 Aktif' if self._explore_active else '❌ Pasif'}\n"
        )

        global _action_name
        if _action_name:
            msg += f"\n⏳ Devam eden işlem: {_action_name}"

        try:
            msg += f"\nURL: {self.driver.current_url[:80]}"
        except Exception:
            msg += "\nURL: (tarayıcı erişilemez)"

        send_telegram_message(msg)

    def _cmd_screenshot(self):
        try:
            take_screenshot(self.driver, "📸 Screenshot")
        except Exception as e:
            send_telegram_message(f"❌ Screenshot alınamadı: {e}")

    # ──────────────────────────────────────────────────────────
    #  KOMUT HANDLER'LARI — SİSTEM
    # ──────────────────────────────────────────────────────────
    def _cmd_cancel(self):
        """Python process'ini durdur."""
        send_telegram_message(
            "🛑 <b>İhlamur durduruluyor...</b>\nProcess sonlandırılacak."
        )
        log.info("🛑 /cancel komutu — process sonlandırılıyor...")

        self._explore_active = False

        # SIGINT göndererek ana thread'deki sleep'i keser → finally bloğu temizliği yapar
        os.kill(os.getpid(), signal.SIGINT)

    def _cmd_help(self):
        send_telegram_message(
            "🌳 <b>İhlamur Bot Komutları</b>\n\n"
            "<b>Oturum:</b>\n"
            "/login — Giriş yap (cookie → tam giriş)\n"
            "/relogin — Sıfırdan giriş yap\n"
            "/logout — Çıkış yap\n\n"
            "<b>İzleme:</b>\n"
            "/status — Oturum durumu\n"
            "/screenshot — Ekran görüntüsü\n\n"
            "<b>Keşif:</b>\n"
            "/explore — İnteraktif sayfa keşfi\n\n"
            "<b>Sistem:</b>\n"
            "/cancel — Botu durdur\n"
            "/help — Bu mesaj"
        )

    # ──────────────────────────────────────────────────────────
    #  EXPLORE MODU — İNTERAKTİF UZAKTAN KUMANDA
    # ──────────────────────────────────────────────────────────
    def _cmd_explore(self):
        """Explore modunu aç/kapat (toggle)."""
        if self._explore_active:
            self._explore_active = False
            send_telegram_message("✅ Explore modu kapatıldı.")
            return

        self._explore_active = True

        send_telegram_message(
            "🔍 <b>Explore Modu Aktif</b>\n\n"
            "Komutlar (<b>/</b> olmadan yazın):\n"
            "• <code>tıkla #id</code> — ID ile tıkla\n"
            "• <code>tıkla .class</code> — CSS class ile tıkla\n"
            "• <code>tıkla //xpath</code> — XPath ile tıkla\n"
            '• <code>tıkla "metin"</code> — Link text ile tıkla\n'
            "• <code>yaz #id metin</code> — Elemente yaz\n"
            "• <code>git https://url</code> — URL'ye git\n"
            "• <code>scroll aşağı</code> / <code>yukarı</code>\n"
            "• <code>bekle 5</code> — N saniye bekle\n"
            "• <code>js alert('test')</code> — JavaScript çalıştır\n"
            "• <code>scan</code> — Sayfayı tekrar tara\n"
            "• <code>bitti</code> — Explore modundan çık\n"
        )

        self._explore_scan_page()

    def _explore_handle_message(self, text: str):
        """Explore modundayken gelen serbest mesajları işler."""
        text = text.strip()
        lower = text.lower()

        try:
            # ── bitti ─────────────────────────────────────────
            if lower in ("bitti", "çık", "exit", "quit"):
                self._explore_active = False
                send_telegram_message("✅ Explore modu kapatıldı.")
                return

            # ── tıkla ────────────────────────────────────────
            if lower.startswith("tıkla ") or lower.startswith("tikla "):
                selector = text.split(None, 1)[1].strip()
                self._explore_click(selector)
                return

            # ── yaz ───────────────────────────────────────────
            if lower.startswith("yaz "):
                parts = text.split(None, 2)  # yaz #id metin
                if len(parts) < 3:
                    send_telegram_message(
                        "⚠️ Kullanım: <code>yaz #elementId metin</code>"
                    )
                    return
                selector = parts[1].strip()
                value = parts[2].strip()
                self._explore_type(selector, value)
                return

            # ── git ───────────────────────────────────────────
            if lower.startswith("git "):
                url = text.split(None, 1)[1].strip()
                self._explore_navigate(url)
                return

            # ── scroll ────────────────────────────────────────
            if lower.startswith("scroll "):
                direction = text.split(None, 1)[1].strip().lower()
                self._explore_scroll(direction)
                return

            # ── bekle ─────────────────────────────────────────
            if lower.startswith("bekle "):
                try:
                    seconds = min(int(text.split(None, 1)[1]), 30)
                    send_telegram_message(f"⏳ {seconds} saniye bekleniyor...")
                    time.sleep(seconds)
                    take_screenshot(self.driver, f"⏳ {seconds}s sonra")
                except ValueError:
                    send_telegram_message("⚠️ Kullanım: <code>bekle 5</code>")
                return

            # ── js ────────────────────────────────────────────
            if lower.startswith("js "):
                code = text.split(None, 1)[1].strip()
                self._explore_js(code)
                return

            # ── scan ──────────────────────────────────────────
            if lower in ("scan", "tara", "listele"):
                self._explore_scan_page()
                return

            # ── Bilinmeyen ────────────────────────────────────
            send_telegram_message(
                "❓ Anlaşılamadı. Komutlar:\n"
                "<code>tıkla</code>, <code>yaz</code>, <code>git</code>, "
                "<code>scroll</code>, <code>bekle</code>, <code>js</code>, "
                "<code>scan</code>, <code>bitti</code>"
            )

        except Exception as e:
            log.error(f"Explore hatası: {e}")
            send_telegram_message(f"❌ Explore hatası: {e}")

    # ── EXPLORE: Element bulma ────────────────────────────────
    def _explore_find_element(self, selector: str):
        """
        Selector → element:
          #id        → By.ID
          //xpath    → By.XPATH
          "metin"    → By.LINK_TEXT → PARTIAL_LINK_TEXT
          'metin'    → aynı
          diğer      → By.CSS_SELECTOR
        """
        s = selector.strip()

        if s.startswith("#") and " " not in s:
            return self.driver.find_element(By.ID, s[1:])

        if s.startswith("//") or s.startswith("(//"):
            return self.driver.find_element(By.XPATH, s)

        if (s.startswith('"') and s.endswith('"')) or (
            s.startswith("'") and s.endswith("'")
        ):
            link_text = s.strip("\"'")
            try:
                return self.driver.find_element(By.LINK_TEXT, link_text)
            except NoSuchElementException:
                return self.driver.find_element(By.PARTIAL_LINK_TEXT, link_text)

        return self.driver.find_element(By.CSS_SELECTOR, s)

    # ── EXPLORE: Tıkla ───────────────────────────────────────
    def _explore_click(self, selector: str):
        try:
            el = self._explore_find_element(selector)
            tag = el.tag_name
            el_id = el.get_attribute("id") or ""
            el_text = (el.text or "")[:30]

            try:
                el.click()
            except ElementNotInteractableException:
                self.driver.execute_script("arguments[0].click();", el)

            time.sleep(1.5)
            send_telegram_message(
                f"✅ Tıklandı: <code>{selector}</code>\n"
                f"   ({tag} id={el_id} text={el_text})"
            )
            take_screenshot(self.driver, "🖱 Tıklama sonrası")

        except NoSuchElementException:
            send_telegram_message(f"❌ Element bulunamadı: <code>{selector}</code>")
        except Exception as e:
            send_telegram_message(f"❌ Tıklama hatası: {e}")

    # ── EXPLORE: Yaz ──────────────────────────────────────────
    def _explore_type(self, selector: str, value: str):
        try:
            el = self._explore_find_element(selector)

            self.driver.execute_script(
                """
                var el = arguments[0], text = arguments[1];
                el.focus();
                el.value = '';
                el.value = text;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                """,
                el,
                value,
            )

            time.sleep(0.5)
            send_telegram_message(
                f"✅ Yazıldı: <code>{selector}</code> ← <code>{value}</code>"
            )
            take_screenshot(self.driver, "⌨️ Yazma sonrası")

        except NoSuchElementException:
            send_telegram_message(f"❌ Element bulunamadı: <code>{selector}</code>")
        except Exception as e:
            send_telegram_message(f"❌ Yazma hatası: {e}")

    # ── EXPLORE: Git ──────────────────────────────────────────
    def _explore_navigate(self, url: str):
        try:
            if not url.startswith("http"):
                url = "https://" + url

            send_telegram_message(f"🌐 Gidiliyor: {url[:80]}")
            self.driver.get(url)
            time.sleep(3)
            send_telegram_message(f"✅ Yüklendi: {self.driver.current_url[:80]}")
            take_screenshot(self.driver, "🌐 Navigasyon")

        except Exception as e:
            send_telegram_message(f"❌ Navigasyon hatası: {e}")

    # ── EXPLORE: Scroll ───────────────────────────────────────
    def _explore_scroll(self, direction: str):
        try:
            scripts = {
                "aşağı": "window.scrollBy(0, 500);",
                "asagi": "window.scrollBy(0, 500);",
                "down": "window.scrollBy(0, 500);",
                "yukarı": "window.scrollBy(0, -500);",
                "yukari": "window.scrollBy(0, -500);",
                "up": "window.scrollBy(0, -500);",
                "en aşağı": "window.scrollTo(0, document.body.scrollHeight);",
                "en asagi": "window.scrollTo(0, document.body.scrollHeight);",
                "bottom": "window.scrollTo(0, document.body.scrollHeight);",
                "en yukarı": "window.scrollTo(0, 0);",
                "en yukari": "window.scrollTo(0, 0);",
                "top": "window.scrollTo(0, 0);",
            }

            script = scripts.get(direction)
            if not script:
                send_telegram_message(
                    "⚠️ <code>scroll aşağı/yukarı/en aşağı/en yukarı</code>"
                )
                return

            self.driver.execute_script(script)
            time.sleep(0.5)
            take_screenshot(self.driver, f"📜 Scroll {direction}")

        except Exception as e:
            send_telegram_message(f"❌ Scroll hatası: {e}")

    # ── EXPLORE: JavaScript ───────────────────────────────────
    def _explore_js(self, code: str):
        try:
            result = self.driver.execute_script(code)
            result_str = str(result)[:500] if result is not None else "(void)"

            send_telegram_message(
                f"✅ JS:\n<code>{code[:200]}</code>\n\nSonuç: <code>{result_str}</code>"
            )
            take_screenshot(self.driver, "🔧 JS sonrası")

        except Exception as e:
            send_telegram_message(f"❌ JS hatası: {e}")

    # ── EXPLORE: Sayfa tarama ─────────────────────────────────
    def _explore_scan_page(self):
        """Sayfadaki tıklanabilir element ve input alanlarını listeler."""
        try:
            take_screenshot(self.driver, "🔍 Explore")

            url = self.driver.current_url[:80]
            title = self.driver.title[:60]

            elements_json = self.driver.execute_script("""
                var results = [];
                var seen = new Set();

                // Linkler
                var links = document.querySelectorAll('a[href]');
                for (var i = 0; i < links.length && results.length < 15; i++) {
                    var el = links[i];
                    var text = (el.textContent || '').trim().substring(0, 40);
                    if (!text || seen.has(text)) continue;
                    seen.add(text);
                    var rect = el.getBoundingClientRect();
                    if (rect.width === 0 && rect.height === 0) continue;
                    results.push({
                        tag: 'a', id: el.id || '', text: text,
                        href: (el.href || '').substring(0, 60)
                    });
                }

                // Butonlar
                var btns = document.querySelectorAll(
                    'button, input[type="submit"], input[type="button"]'
                );
                for (var i = 0; i < btns.length && results.length < 25; i++) {
                    var el = btns[i];
                    var text = (el.textContent || el.value || '').trim().substring(0, 40);
                    if (!text || seen.has(text)) continue;
                    seen.add(text);
                    var rect = el.getBoundingClientRect();
                    if (rect.width === 0 && rect.height === 0) continue;
                    results.push({
                        tag: el.tagName.toLowerCase(), id: el.id || '',
                        text: text, type: el.type || ''
                    });
                }

                // Input alanları (görünür)
                var inputs = document.querySelectorAll(
                    'input[type="text"], input[type="password"], '
                    + 'input[type="email"], input[type="number"], '
                    + 'input[type="tel"], textarea, select, '
                    + 'div[contenteditable="true"]'
                );
                for (var i = 0; i < inputs.length && results.length < 35; i++) {
                    var el = inputs[i];
                    var rect = el.getBoundingClientRect();
                    if (rect.width === 0 && rect.height === 0) continue;
                    results.push({
                        tag: el.tagName.toLowerCase(), id: el.id || '',
                        name: el.name || '',
                        type: el.type || (el.contentEditable ? 'contenteditable' : ''),
                        placeholder: (el.placeholder || '').substring(0, 30)
                    });
                }

                return results;
            """)

            msg = f"🔍 <b>Sayfa Taraması</b>\n\nURL: {url}\nTitle: {title}\n\n"

            if not elements_json:
                msg += "Tıklanabilir element bulunamadı."
            else:
                # Tıklanabilir
                clickables = [
                    e
                    for e in elements_json
                    if e["tag"] in ("a", "button", "input") and e.get("text")
                ]
                if clickables:
                    msg += "<b>🖱 Tıklanabilir:</b>\n"
                    for e in clickables:
                        eid = e.get("id", "")
                        hint = f"#{eid}" if eid else f"\"{e['text']}\""
                        msg += f"  • <code>tıkla {hint}</code> — {e['text'][:35]}\n"

                # Giriş alanları
                form_inputs = [
                    e
                    for e in elements_json
                    if e["tag"] in ("input", "textarea", "select", "div")
                    and (e.get("name") or e.get("id") or e.get("placeholder"))
                ]
                if form_inputs:
                    msg += "\n<b>⌨️ Giriş Alanları:</b>\n"
                    for e in form_inputs:
                        eid = e.get("id", "")
                        ename = e.get("name", "")
                        label = eid or ename or e.get("placeholder", "?")
                        hint = (
                            f"#{eid}"
                            if eid
                            else f"[name=\"{ename}\"]"
                            if ename
                            else "?"
                        )
                        msg += f"  • <code>yaz {hint} değer</code> — {label}\n"

            if len(msg) > 4000:
                msg = msg[:4000] + "\n...(kesildi)"

            send_telegram_message(msg)

        except Exception as e:
            log.error(f"Explore scan hatası: {e}")
            send_telegram_message(f"❌ Tarama hatası: {e}")

    # ──────────────────────────────────────────────────────────
    #  PROPERTY
    # ──────────────────────────────────────────────────────────
    @property
    def is_running(self) -> bool:
        return self._polling_thread is not None and self._polling_thread.is_alive()
