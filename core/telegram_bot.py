"""
İhlamur — Telegram Komut Botu.

Telegram üzerinden bot komutlarıyla sistemi kontrol eder:
  /login     — Oturum aç (önce cookie dener, yoksa tam giriş)
  /relogin   — Cookie'leri sil, sıfırdan giriş yap
  /logout    — Oturumu kapat
  /status    — Oturum durumu
  /screenshot — Anlık ekran görüntüsü
  /help      — Komut listesi

Tasarım kararları (loop'a girmemek için):
  • Tek bir polling thread'i var — komutları okur, handler'a yönlendirir.
  • Her handler kendi thread'inde çalışır ama bir Lock ile korunur:
    aynı anda 2 login/logout çalışamaz.
  • '/' ile başlayan mesajlar CAPTCHA polling'ine GİTMEZ —
    _wait_for_captcha_from_telegram sadece '/' ile başlamayanları alır.
  • Bot kendi gönderdiği mesajlara tepki vermez (sadece TELEGRAM_CHAT_ID).
"""

import threading
import time
import requests

from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from utils.logger import get_logger
from utils.helpers import send_telegram_message, take_screenshot

log = get_logger(__name__)

# ── Komut gönderildi ama işlem devam ediyor koruması ──────
_action_lock = threading.Lock()
_action_name: str = ""  # Şu an çalışan işlem adı


class TelegramBot:
    """
    Telegram long-polling ile komut dinleyen bot.
    Browser/Auth/Session nesneleri dışarıdan enjekte edilir.
    """

    def __init__(self, auth, session, driver):
        """
        Args:
            auth:    core.auth.Auth instance
            session: core.session.SessionManager instance
            driver:  selenium WebDriver instance
        """
        self.auth = auth
        self.session = session
        self.driver = driver

        self._polling_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_update_id: int = 0

    # ──────────────────────────────────────────────────────────
    #  BAŞLAT / DURDUR
    # ──────────────────────────────────────────────────────────
    def start(self):
        """Polling thread'ini başlatır."""
        if self._polling_thread and self._polling_thread.is_alive():
            log.warning("Telegram bot zaten çalışıyor.")
            return

        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            log.error("TELEGRAM_BOT_TOKEN veya TELEGRAM_CHAT_ID eksik!")
            return

        self._stop_event.clear()

        # Mevcut update offset'ini al (eski mesajları atla)
        self._flush_pending_updates()

        self._polling_thread = threading.Thread(
            target=self._polling_loop, daemon=True, name="telegram-bot"
        )
        self._polling_thread.start()
        log.info("🤖 Telegram komut botu başlatıldı.")

    def stop(self):
        """Polling thread'ini durdurur."""
        if self._polling_thread and self._polling_thread.is_alive():
            self._stop_event.set()
            self._polling_thread.join(timeout=15)
        self._polling_thread = None
        log.info("🤖 Telegram komut botu durduruldu.")

    # ──────────────────────────────────────────────────────────
    #  POLLING
    # ──────────────────────────────────────────────────────────
    def _flush_pending_updates(self):
        """Başlatılmadan önceki tüm mesajları atla."""
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
            resp = requests.get(url, params={"offset": -1, "limit": 1}, timeout=10)
            data = resp.json()
            if data.get("result"):
                self._last_update_id = data["result"][-1]["update_id"]
                log.info(f"Telegram offset: {self._last_update_id} (eski mesajlar atlandı)")
        except Exception as e:
            log.warning(f"Telegram flush hatası: {e}")

    def _polling_loop(self):
        """Ana polling döngüsü — sadece komutları işler."""
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"

        while not self._stop_event.is_set():
            try:
                resp = requests.get(
                    url,
                    params={
                        "offset": self._last_update_id + 1,
                        "timeout": 10,  # long polling
                        "allowed_updates": '["message"]',
                    },
                    timeout=20,
                )
                data = resp.json()

                for update in data.get("result", []):
                    self._last_update_id = update["update_id"]
                    self._handle_update(update)

            except requests.exceptions.Timeout:
                continue  # Normal — long polling timeout
            except Exception as e:
                log.error(f"Telegram polling hatası: {e}")
                # Hata durumunda kısa bekle, tekrar dene
                self._stop_event.wait(5)

    def _handle_update(self, update: dict):
        """Tek bir Telegram update'ini işler."""
        msg = update.get("message", {})
        chat_id = str(msg.get("chat", {}).get("id", ""))
        text = (msg.get("text") or "").strip()

        # Sadece bizim chat'ten gelen mesajları işle
        if chat_id != str(TELEGRAM_CHAT_ID):
            return

        # Komut değilse atla (CAPTCHA polling'ine bırak)
        if not text.startswith("/"):
            return

        command = text.split()[0].lower()  # /login@BotName → /login
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
            "/help": self._cmd_help,
            "/start": self._cmd_help,
        }

        handler = handlers.get(command)
        if handler:
            # Status/screenshot/help anında çalışabilir, lock gerekmez
            if command in ("/status", "/screenshot", "/ss", "/help", "/start"):
                threading.Thread(
                    target=handler, daemon=True, name=f"cmd-{command}"
                ).start()
            else:
                # Login/logout gibi işlemler lock ile korunur
                threading.Thread(
                    target=self._run_with_lock,
                    args=(command, handler),
                    daemon=True,
                    name=f"cmd-{command}",
                ).start()
        else:
            send_telegram_message(f"❓ Bilinmeyen komut: <code>{command}</code>\n/help yazın.")

    # ──────────────────────────────────────────────────────────
    #  LOCK MEKANİZMASI
    # ──────────────────────────────────────────────────────────
    def _run_with_lock(self, command: str, handler):
        """
        Handler'ı lock ile çalıştırır.
        Aynı anda 2 işlem çalışmasını engeller (loop koruması).
        """
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
    #  KOMUT HANDLER'LARI
    # ──────────────────────────────────────────────────────────
    def _cmd_login(self):
        """Oturum aç — önce cookie dener."""
        send_telegram_message("🔑 <b>Giriş başlatılıyor...</b>\nÖnce cookie ile denenecek.")

        # Önce cookie restore dene
        if self.session.try_restore_session():
            self.auth.is_logged_in = True
            send_telegram_message("✅ <b>Oturum cookie ile geri yüklendi!</b>")
            return

        # Cookie başarısız → tam login
        send_telegram_message("🔐 Cookie geçersiz, tam giriş yapılıyor...")
        self.auth.login()

        if self.auth.is_logged_in:
            send_telegram_message("✅ <b>Giriş başarılı!</b>")
        else:
            send_telegram_message("❌ <b>Giriş başarısız!</b>")

    def _cmd_relogin(self):
        """Cookie'leri sil, sıfırdan giriş yap."""
        send_telegram_message("🔄 <b>Yeniden giriş başlatılıyor...</b>\nCookie'ler siliniyor.")

        # Önce logout dene (sessizce)
        try:
            if self.auth.is_logged_in:
                self.auth.logout()
        except Exception:
            pass

        # Cookie'leri sil
        self.session._delete_cookie_file()
        self.auth.is_logged_in = False

        # Sıfırdan login
        send_telegram_message("🔐 Sıfırdan giriş yapılıyor...")
        self.auth.login()

        if self.auth.is_logged_in:
            send_telegram_message("✅ <b>Yeniden giriş başarılı!</b>")
        else:
            send_telegram_message("❌ <b>Yeniden giriş başarısız!</b>")

    def _cmd_logout(self):
        """Oturumu kapat."""
        if not self.auth.is_logged_in:
            send_telegram_message("ℹ️ Zaten giriş yapılmamış.")
            return

        send_telegram_message("🔓 <b>Çıkış yapılıyor...</b>")

        self.auth.logout()
        self.session._delete_cookie_file()

        send_telegram_message("✅ <b>Çıkış yapıldı.</b> Cookie'ler silindi.")

    def _cmd_status(self):
        """Oturum durumu bilgisi."""
        info = self.session.session_info()
        logged_in = self.auth.is_logged_in

        status_emoji = "🟢" if logged_in else "🔴"

        msg = (
            f"{status_emoji} <b>İhlamur Durum</b>\n\n"
            f"Oturum: {'Açık' if logged_in else 'Kapalı'}\n"
            f"Cookie dosyası: {'✅ Var' if info['cookie_file_exists'] else '❌ Yok'}\n"
        )

        if info["cookie_file_exists"]:
            msg += (
                f"Cookie yaşı: {info['session_age_minutes']:.1f} dk\n"
                f"Max yaş: {info['max_age_seconds'] / 60:.0f} dk\n"
                f"Son kayıt: {info['saved_at']}\n"
            )

        msg += f"Keep-alive: {'✅ Aktif' if info['keepalive_running'] else '❌ Pasif'}\n"

        global _action_name
        if _action_name:
            msg += f"\n⏳ Devam eden işlem: {_action_name}"

        try:
            msg += f"\nURL: {self.driver.current_url[:60]}"
        except Exception:
            msg += "\nURL: (tarayıcı erişilemez)"

        send_telegram_message(msg)

    def _cmd_screenshot(self):
        """Anlık ekran görüntüsü al."""
        try:
            take_screenshot(self.driver, "📸 Manuel screenshot")
        except Exception as e:
            send_telegram_message(f"❌ Screenshot alınamadı: {e}")

    def _cmd_help(self):
        """Komut listesi."""
        send_telegram_message(
            "🌳 <b>İhlamur Bot Komutları</b>\n\n"
            "/login — Giriş yap (cookie → tam giriş)\n"
            "/relogin — Sıfırdan giriş yap\n"
            "/logout — Çıkış yap\n"
            "/status — Oturum durumu\n"
            "/screenshot — Ekran görüntüsü\n"
            "/help — Bu mesaj"
        )

    # ──────────────────────────────────────────────────────────
    #  PROPERTY
    # ──────────────────────────────────────────────────────────
    @property
    def is_running(self) -> bool:
        return self._polling_thread is not None and self._polling_thread.is_alive()
