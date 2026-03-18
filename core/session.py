"""
KuveytTürk İnternet Şubesi — Oturum Yönetimi.

Cookie'leri diske kaydeder, yükler ve oturumun hâlâ geçerli olup
olmadığını periyodik olarak kontrol eder. Oturum sona erdiğinde
Telegram bildirimi gönderir ve isteğe bağlı otomatik yeniden giriş yapar.
"""

import json
import os
import time
import threading
from datetime import datetime
from selenium.webdriver.common.by import By

from config.settings import (
    SESSION_DIR,
    SESSION_COOKIE_FILE,
    SESSION_CHECK_INTERVAL,
    SESSION_KEEPALIVE_URL,
    SESSION_MAX_AGE,
)
from utils.logger import get_logger
from utils.helpers import take_screenshot, send_telegram_message

log = get_logger(__name__)


class SessionManager:
    """Cookie tabanlı oturum yöneticisi."""

    def __init__(self, driver):
        self.driver = driver
        self._last_save_time: float = 0
        self._session_start: float = 0
        self._keepalive_thread: threading.Thread | None = None
        self._popup_watcher_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        os.makedirs(SESSION_DIR, exist_ok=True)

    # ──────────────────────────────────────────────────────────
    #  COOKIE KAYDET / YÜKLE
    # ──────────────────────────────────────────────────────────
    def save_cookies(self) -> bool:
        """Mevcut tarayıcı cookie'lerini JSON dosyasına kaydeder."""
        try:
            cookies = self.driver.get_cookies()
            if not cookies:
                log.warning("Kaydedilecek cookie bulunamadı.")
                return False

            data = {
                "cookies": cookies,
                "saved_at": datetime.now().isoformat(),
                "saved_ts": time.time(),
                "url": self.driver.current_url,
            }

            with open(SESSION_COOKIE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)

            self._last_save_time = time.time()
            self._session_start = time.time()
            log.info(f"✅ {len(cookies)} cookie kaydedildi → {SESSION_COOKIE_FILE}")
            return True

        except Exception as e:
            log.error(f"Cookie kaydetme hatası: {e}")
            return False

    def load_cookies(self) -> bool:
        """
        Daha önce kaydedilmiş cookie'leri tarayıcıya yükler.
        Cookie dosyası yoksa veya çok eskiyse False döner.
        """
        if not os.path.exists(SESSION_COOKIE_FILE):
            log.info("Cookie dosyası bulunamadı — ilk giriş gerekli.")
            return False

        try:
            with open(SESSION_COOKIE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            saved_ts = data.get("saved_ts", 0)
            age = time.time() - saved_ts

            if age > SESSION_MAX_AGE:
                log.warning(
                    f"Cookie dosyası çok eski ({age:.0f}s > {SESSION_MAX_AGE}s). "
                    "Yeniden giriş gerekli."
                )
                self._delete_cookie_file()
                return False

            cookies = data.get("cookies", [])
            if not cookies:
                log.warning("Cookie dosyası boş.")
                return False

            # Önce domain'e git ki cookie'ler set edilebilsin
            self.driver.get(SESSION_KEEPALIVE_URL)
            time.sleep(2)

            # Tüm cookie'leri yükle
            loaded = 0
            for cookie in cookies:
                try:
                    # Selenium bazı alanları kabul etmiyor, temizle
                    for key in ["sameSite", "storeId"]:
                        cookie.pop(key, None)
                    # expiry float olabilir, int'e çevir
                    if "expiry" in cookie:
                        cookie["expiry"] = int(cookie["expiry"])
                    self.driver.add_cookie(cookie)
                    loaded += 1
                except Exception as e:
                    log.debug(f"Cookie yüklenemedi ({cookie.get('name', '?')}): {e}")

            log.info(f"✅ {loaded}/{len(cookies)} cookie yüklendi (yaş: {age:.0f}s)")
            self._session_start = saved_ts
            self._last_save_time = saved_ts
            return loaded > 0

        except (json.JSONDecodeError, KeyError) as e:
            log.error(f"Cookie dosyası bozuk: {e}")
            self._delete_cookie_file()
            return False
        except Exception as e:
            log.error(f"Cookie yükleme hatası: {e}")
            return False

    def _delete_cookie_file(self):
        """Cookie dosyasını siler."""
        try:
            if os.path.exists(SESSION_COOKIE_FILE):
                os.remove(SESSION_COOKIE_FILE)
                log.info("Cookie dosyası silindi.")
        except Exception as e:
            log.warning(f"Cookie dosyası silinemedi: {e}")

    # ──────────────────────────────────────────────────────────
    #  OTURUM GEÇERLİLİK KONTROLÜ
    # ──────────────────────────────────────────────────────────
    def is_session_valid(self) -> bool:
        """
        Mevcut oturumun hâlâ geçerli olup olmadığını kontrol eder.
        Dashboard sayfasını yükleyip, login sayfasına yönlendirilip
        yönlendirilmediğimize bakar.
        """
        try:
            current_url = self.driver.current_url

            # Dashboard veya herhangi bir iç sayfaya git
            self.driver.get(SESSION_KEEPALIVE_URL)
            time.sleep(3)

            new_url = self.driver.current_url

            # Login sayfasına yönlendirildiyse → oturum sona ermiş
            if "Login" in new_url or "InitialLogin" in new_url:
                log.warning("⚠️ Oturum geçersiz — login sayfasına yönlendirildi.")
                return False

            # Sayfa içeriğinde dashboard elementleri var mı?
            try:
                page_text = self.driver.find_element(By.TAG_NAME, "body").text
                dashboard_keywords = [
                    "Hesaplarım", "Hesap Özeti", "Bakiye",
                    "Havale", "EFT", "Döviz", "Yatırım",
                ]
                if any(kw in page_text for kw in dashboard_keywords):
                    log.info("✅ Oturum geçerli — dashboard erişilebilir.")
                    return True
            except Exception:
                pass

            # URL login değilse ama dashboard da değilse → kontrol et
            if "Login" not in new_url:
                log.info("Oturum muhtemelen geçerli (URL login dışı).")
                return True

            return False

        except Exception as e:
            log.error(f"Oturum kontrolü hatası: {e}")
            return False

    def try_restore_session(self) -> bool:
        """
        Kayıtlı cookie'lerle oturumu geri yüklemeyi dener.
        Cookie yükleme + geçerlilik kontrolü yapar.
        Başarılıysa True, değilse False döner.
        """
        log.info("🔄 Mevcut oturum geri yüklenmeye çalışılıyor...")

        if not self.load_cookies():
            log.info("Cookie yüklenemedi — yeni giriş gerekli.")
            return False

        # Cookie'ler yüklendi, şimdi sayfayı yenile ve kontrol et
        self.driver.get(SESSION_KEEPALIVE_URL)
        time.sleep(3)

        if self.is_session_valid():
            age = time.time() - self._session_start
            log.info(f"✅ Oturum başarıyla geri yüklendi! (yaş: {age:.0f}s)")
            send_telegram_message(
                f"🔄 <b>Oturum geri yüklendi</b>\n"
                f"Cookie yaşı: {age:.0f} saniye\n"
                f"Yeni giriş yapılmadı."
            )
            # Cookie'leri güncelle (yeni expiry'ler olabilir)
            self.save_cookies()
            return True

        log.warning("Cookie'ler yüklendi ama oturum geçersiz.")
        self._delete_cookie_file()
        return False

    # ──────────────────────────────────────────────────────────
    #  KEEP-ALIVE (ARKA PLAN)
    # ──────────────────────────────────────────────────────────
    def start_keepalive(self, on_session_expired=None):
        """
        Arka planda oturum canlılık kontrolü başlatır.
        Ayrıca popup watcher'ı da başlatır (Zaman Aşımı popup'ı otomatik kapatma).
        
        Args:
            on_session_expired: Oturum sona erdiğinde çağrılacak callback.
                                None ise sadece Telegram bildirimi gönderilir.
        """
        if self._keepalive_thread and self._keepalive_thread.is_alive():
            log.warning("Keep-alive zaten çalışıyor.")
            return

        self._stop_event.clear()

        # Popup watcher'ı da başlat
        self.start_popup_watcher()

        def _keepalive_loop():
            log.info(
                f"🔄 Keep-alive başlatıldı (kontrol aralığı: {SESSION_CHECK_INTERVAL}s)"
            )
            send_telegram_message(
                f"🔄 <b>Oturum izleme aktif</b>\n"
                f"Kontrol aralığı: {SESSION_CHECK_INTERVAL} saniye"
            )

            consecutive_failures = 0

            while not self._stop_event.is_set():
                self._stop_event.wait(SESSION_CHECK_INTERVAL)
                if self._stop_event.is_set():
                    break

                try:
                    if self.is_session_valid():
                        consecutive_failures = 0
                        # Cookie'leri periyodik güncelle
                        if time.time() - self._last_save_time > 300:  # 5 dk'da bir
                            self.save_cookies()
                            log.debug("Cookie'ler güncellendi (periyodik).")
                    else:
                        consecutive_failures += 1
                        log.warning(
                            f"⚠️ Oturum kontrolü başarısız "
                            f"({consecutive_failures}. deneme)"
                        )

                        if consecutive_failures >= 2:
                            # 2 ardışık başarısızlık → oturum kesin sona ermiş
                            session_age = time.time() - self._session_start
                            log.error("❌ Oturum sona erdi!")
                            send_telegram_message(
                                "❌ <b>Oturum Sona Erdi!</b>\n"
                                f"⏱ Oturum süresi: {session_age:.0f} saniye "
                                f"({session_age / 60:.1f} dakika)\n"
                                "🔄 Yeniden giriş yapılacak..."
                            )
                            self._delete_cookie_file()

                            if on_session_expired:
                                try:
                                    on_session_expired()
                                    consecutive_failures = 0
                                except Exception as e:
                                    log.error(f"Yeniden giriş hatası: {e}")
                                    send_telegram_message(
                                        f"❌ <b>Yeniden giriş başarısız!</b>\n"
                                        f"Hata: {e}"
                                    )
                                    break
                            else:
                                break

                except Exception as e:
                    log.error(f"Keep-alive döngü hatası: {e}")

            log.info("Keep-alive durduruldu.")

        self._keepalive_thread = threading.Thread(
            target=_keepalive_loop, daemon=True, name="session-keepalive"
        )
        self._keepalive_thread.start()

    def stop_keepalive(self):
        """Keep-alive döngüsünü durdurur."""
        if self._keepalive_thread and self._keepalive_thread.is_alive():
            log.info("Keep-alive durduruluyor...")
            self._stop_event.set()
            self._keepalive_thread.join(timeout=10)
            log.info("Keep-alive durduruldu.")
        self._keepalive_thread = None

    # ──────────────────────────────────────────────────────────
    #  BİLGİ
    # ──────────────────────────────────────────────────────────
    def session_info(self) -> dict:
        """Mevcut oturum bilgilerini döner."""
        cookie_exists = os.path.exists(SESSION_COOKIE_FILE)
        age = 0
        saved_at = None

        if cookie_exists:
            try:
                with open(SESSION_COOKIE_FILE, "r") as f:
                    data = json.load(f)
                age = time.time() - data.get("saved_ts", 0)
                saved_at = data.get("saved_at", "?")
            except Exception:
                pass

        return {
            "cookie_file_exists": cookie_exists,
            "session_age_seconds": age,
            "session_age_minutes": age / 60,
            "saved_at": saved_at,
            "max_age_seconds": SESSION_MAX_AGE,
            "keepalive_running": (
                self._keepalive_thread is not None
                and self._keepalive_thread.is_alive()
            ),
            "popup_watcher_running": (
                self._popup_watcher_thread is not None
                and self._popup_watcher_thread.is_alive()
            ),
        }

    # ──────────────────────────────────────────────────────────
    #  ZAMAN AŞIMI POPUP WATCHER
    # ──────────────────────────────────────────────────────────
    def start_popup_watcher(self):
        """
        Arka planda "Zaman Aşımı — Ek süre ister misiniz?" popup'ını
        izler ve otomatik EVET'e basar.

        KuveytTürk İnternet Şubesi oturum süre aşımına yaklaştığında
        modal bir dialog açar:
          - Başlık: "Zaman Aşımı"
          - İçerik: "Kalan Süre: 30 — Oturumunuz kapanmak üzere. Ek süre ister misiniz?"
          - Butonlar: EVET, HAYIR
        """
        if self._popup_watcher_thread and self._popup_watcher_thread.is_alive():
            log.debug("Popup watcher zaten çalışıyor.")
            return

        def _popup_loop():
            log.info("👁 Popup watcher başlatıldı (10s aralık).")
            while not self._stop_event.is_set():
                self._stop_event.wait(10)
                if self._stop_event.is_set():
                    break
                try:
                    self._dismiss_timeout_popup()
                except Exception as e:
                    log.debug(f"Popup kontrol hatası (önemsiz): {e}")
            log.info("👁 Popup watcher durduruldu.")

        self._popup_watcher_thread = threading.Thread(
            target=_popup_loop, daemon=True, name="popup-watcher"
        )
        self._popup_watcher_thread.start()

    def _dismiss_timeout_popup(self):
        """
        Zaman Aşımı popup'ı açıksa EVET butonuna basar.
        Popup yoksa sessizce döner.
        """
        try:
            # Modal dialog içindeki EVET butonu — birkaç olası selector
            evet_btn = self.driver.find_elements(
                By.XPATH,
                "//div[contains(@class,'modal') or contains(@class,'dialog') "
                "or contains(@class,'popup') or contains(@class,'bootbox')]"
                "//button[normalize-space()='EVET'] | "
                "//div[contains(@class,'modal') or contains(@class,'dialog') "
                "or contains(@class,'popup') or contains(@class,'bootbox')]"
                "//a[normalize-space()='EVET'] | "
                "//button[normalize-space()='EVET'] | "
                "//a[normalize-space()='EVET']"
            )
            for btn in evet_btn:
                if btn.is_displayed():
                    try:
                        btn.click()
                    except Exception:
                        self.driver.execute_script("arguments[0].click();", btn)
                    log.info("⏰ Zaman Aşımı popup'ı otomatik kapatıldı (EVET).")
                    send_telegram_message(
                        "⏰ <b>Oturum süresi uzatıldı</b>\n"
                        "Zaman Aşımı popup'ı otomatik kapatıldı."
                    )
                    return
        except Exception:
            pass
