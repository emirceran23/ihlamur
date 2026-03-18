"""
KuveytTürk Yatırım İşlem modülü.

Keşif tarihi: 2026-03-18
─────────────────────────────────────────────────
Menü yolu (ekran görüntüsü 1):
  Ana Menü → Yatırım → alt grup açılır:

  Yatırım Hesabı Para Transferleri
    • Yatırım Hesabına
    • Yatırım Hesabından Para Transferi
  Para Transferi
    • Hesaba
  Hesap İşlemleri
    • Uygunluk Testi
    • Yatırım Hesapları      ← YATIRIM HESAPLARI sayfası
    • Portföyüm              ← PORTFÖYÜM sayfası
  Fon İşlemleri
    • Fon Alış
    • Fon Satış
    • Emir Takip
  Hisse Senedi İşlemleri    ← HEDEFİMİZ
    • Hisse Alış             ← HİSSE ALIŞ sayfası
    • Hisse Satış
    • Emirlerim
    • Hisse Hareketleri
  Kira Sertifikası İşlemleri
    • Alış / Satış / ...

─────────────────────────────────────────────────
HİSSE ALIŞ sayfası (ekran görüntüsü 4):
  Başlık: "HİSSE ALIŞ"
  ① Hesap seçimi — zaten seçili: 418879 / Yatırım Menkul Değerler Hesabı
  ② Hisse Seçiniz — <select> dropdown  →  "-- Seçiniz --"
  ③ İLERİ butonu  (sonraki adımda lot/fiyat gelecek)

PORTFÖYÜM sayfası (ekran görüntüsü 2):
  Başlık: "PORTFÖYÜM"
  Bölüm: "Bakiye Bilgileri (TL)"
  Satırlar: Toplam Hisse Değeri, Toplam Sukuk Değeri,
            Toplam Fon Değeri, T+2 Cari Bakiye,
            T+1 Cari Bakiye, Toplam Portföy Değeri

YATIRIM HESAPLARI sayfası (ekran görüntüsü 3):
  Başlık: "YATIRIM HESAPLARI"
  TL hesabı  : 97237910-4000
  USD hesabı : 97237910-4001
  Menkul hesabı: 418879  ← hisse alışta kullanılan hesap
─────────────────────────────────────────────────
"""

import time
from enum import Enum
from dataclasses import dataclass
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException
from utils.logger import get_logger
from utils.helpers import take_screenshot, retry, format_price, format_quantity, send_telegram_message
from config.settings import MAX_ORDER_AMOUNT, MAX_DAILY_TRADES

log = get_logger(__name__)


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    LIMIT = "limit"       # Limitli emir
    MARKET = "market"     # Piyasa emri


@dataclass
class Order:
    symbol: str           # THYAO, GARAN, vs.
    side: OrderSide
    quantity: int
    price: float | None = None  # None ise piyasa emri
    order_type: OrderType = OrderType.LIMIT

    def total_value(self) -> float:
        if self.price:
            return self.price * self.quantity
        return 0.0

    def __str__(self) -> str:
        side_str = "ALIŞ" if self.side == OrderSide.BUY else "SATIŞ"
        price_str = format_price(self.price) if self.price else "PİYASA"
        return f"{side_str} | {self.symbol} | {format_quantity(self.quantity)} adet | {price_str}"


@dataclass
class PortfolioItem:
    symbol: str
    quantity: int
    avg_cost: float
    current_price: float
    profit_loss: float
    profit_loss_pct: float


class Trader:
    """TradePlus üzerinde işlem yapar."""

    def __init__(self, driver):
        self.driver = driver
        self.wait = WebDriverWait(driver, 15)
        self.daily_trade_count = 0

    # ──────────────────────────────────────────────────────────
    # Menü Navigasyonu  (keşif 2026-03-18)
    # ──────────────────────────────────────────────────────────

    def navigate_to_investment_menu(self) -> bool:
        """
        Ana menüden 'Yatırım' linkine tıklar → alt menü açılır.
        Keşif: LINK_TEXT "Yatırım" çalışıyor (ekran görüntüsü 1).
        """
        log.info("Yatırım menüsüne gidiliyor...")
        try:
            el = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.LINK_TEXT, "Yatırım"))
            )
            try:
                el.click()
            except Exception:
                self.driver.execute_script("arguments[0].click();", el)
            time.sleep(2)
            log.info(f"✅ Yatırım menüsüne tıklandı. URL: {self.driver.current_url}")
            return True
        except TimeoutException:
            log.warning("⚠️ 'Yatırım' linki bulunamadı!")
            take_screenshot(self.driver, "yatirim_menu_not_found")
            return False

    def _navigate_to_submenu_item(self, link_text: str, page_title_keyword: str) -> bool:
        """
        Yatırım alt menüsündeki bir öğeye gider ve sayfanın yüklendiğini doğrular.
        link_text      : Tıklanacak linkin tam metni (ör. "Hisse Alış")
        page_title_kw  : Yüklenen sayfada aranacak başlık anahtar kelimesi
        """
        if not self.navigate_to_investment_menu():
            return False
        link = self._find_clickable(
            selectors=[
                (By.LINK_TEXT, link_text),
                (By.PARTIAL_LINK_TEXT, link_text),
                (By.XPATH, f"//a[normalize-space()='{link_text}']"),
            ],
            description=link_text,
            timeout=8,
        )
        if not link:
            log.warning(f"⚠️ '{link_text}' linki bulunamadı!")
            take_screenshot(self.driver, f"nav_not_found_{link_text.replace(' ', '_')}")
            return False
        try:
            link.click()
        except Exception:
            self.driver.execute_script("arguments[0].click();", link)
        time.sleep(3)
        # Sayfa başlığı kontrolü
        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(
                    (By.XPATH, f"//*[contains(text(), '{page_title_keyword}')]")
                )
            )
        except TimeoutException:
            log.warning(f"⚠️ '{page_title_keyword}' başlığı bulunamadı, devam ediliyor.")
        log.info(f"✅ '{link_text}' sayfası yüklendi: {self.driver.current_url}")
        return True

    def explore_investment_submenu(self) -> list[dict]:
        """
        Yatırım menüsüne gidip alt menü linklerini listeler.
        Her öğe: {text, href, id} içerir.
        """
        log.info("Yatırım alt menüsü keşfediliyor...")
        take_screenshot(self.driver, "before_investment_menu")

        if not self.navigate_to_investment_menu():
            return []

        take_screenshot(self.driver, "investment_menu_open")

        items = self.driver.execute_script("""
            var results = [];
            var seen = new Set();
            var links = document.querySelectorAll('a[href]');
            for (var i = 0; i < links.length; i++) {
                var el = links[i];
                var text = (el.textContent || '').trim();
                if (!text || seen.has(text)) continue;
                var rect = el.getBoundingClientRect();
                if (rect.width === 0 && rect.height === 0) continue;
                seen.add(text);
                results.push({
                    text: text.substring(0, 60),
                    href: (el.href || '').substring(0, 100),
                    id: el.id || ''
                });
            }
            return results;
        """)

        log.info(f"Yatırım alt menüsünde {len(items)} link bulundu:")
        for item in items:
            log.info(f"  [{item['id'] or '-'}] {item['text']} → {item['href']}")

        return items or []

    # ──────────────────────────────────────────────────────────
    # Emir Gönderme
    # ──────────────────────────────────────────────────────────

    def place_order(self, order: Order) -> bool:
        """
        TradePlus üzerinde emir gönderir.

        NOT: Selector'lar TradePlus arayüzüne göre güncellenmelidir.
        İlk çalıştırmada explore_trade_page() ile sayfa yapısını keşfedin.
        """
        log.info(f"Emir gönderiliyor: {order}")

        # ── Güvenlik kontrolleri ──────────────────────────────
        if not self._safety_checks(order):
            return False

        try:
            # ── Adım 1: İşlem sayfasına git ──────────────────
            self._navigate_to_trade_page()

            # ── Adım 2: Hisse sembolünü gir ──────────────────
            self._enter_symbol(order.symbol)

            # ── Adım 3: Alış/Satış seç ───────────────────────
            self._select_side(order.side)

            # ── Adım 4: Miktarı gir ──────────────────────────
            self._enter_quantity(order.quantity)

            # ── Adım 5: Fiyatı gir (limit emir ise) ──────────
            if order.order_type == OrderType.LIMIT and order.price:
                self._enter_price(order.price)

            # ── Adım 6: Emri gönder ──────────────────────────
            self._submit_order()

            # ── Adım 7: Onay ─────────────────────────────────
            success = self._confirm_order()

            if success:
                self.daily_trade_count += 1
                log.info(f"✅ Emir başarıyla gönderildi: {order}")
                send_telegram_message(f"✅ Emir gönderildi:\n{order}")
            else:
                log.error(f"❌ Emir gönderilemedi: {order}")
                send_telegram_message(f"❌ Emir başarısız:\n{order}")

            return success

        except Exception as e:
            take_screenshot(self.driver, f"order_error_{order.symbol}")
            log.error(f"Emir hatası: {e}")
            send_telegram_message(f"❌ Emir hatası:\n{order}\nHata: {e}")
            raise

    def _safety_checks(self, order: Order) -> bool:
        """Emir öncesi güvenlik kontrolleri."""
        # Günlük işlem limiti
        if self.daily_trade_count >= MAX_DAILY_TRADES:
            log.warning(f"Günlük işlem limiti aşıldı! ({MAX_DAILY_TRADES})")
            return False

        # Tutar limiti
        if order.price and order.total_value() > MAX_ORDER_AMOUNT:
            log.warning(
                f"Emir tutarı limiti aşıyor! "
                f"{format_price(order.total_value())} > {format_price(MAX_ORDER_AMOUNT)}"
            )
            return False

        # Sembol kontrolü
        if not order.symbol or len(order.symbol) < 2:
            log.warning(f"Geçersiz sembol: {order.symbol}")
            return False

        # Miktar kontrolü
        if order.quantity <= 0:
            log.warning(f"Geçersiz miktar: {order.quantity}")
            return False

        return True

    def _navigate_to_trade_page(self):
        """
        Hisse Alış sayfasına gider.
        Yol (keşif 2026-03-18):
          Ana Menü → Yatırım → Hisse Senedi İşlemleri → Hisse Alış
        Sayfa başlığı: "HİSSE ALIŞ"
        """
        log.info("Hisse Alış sayfasına gidiliyor...")
        self._navigate_to_submenu_item("Hisse Alış", "HİSSE ALIŞ")

    def _enter_symbol(self, symbol: str):
        """
        Hisse Seçiniz dropdown'undan sembol seçer.

        HİSSE ALIŞ sayfası (ekran görüntüsü 4):
          - "Hisse Seçiniz" etiketi altında <select> — "-- Seçiniz --" varsayılan.
          - Önce dropdown'u tıkla, ardından sembolü arama/seçme işlemi yap.
          HTML gelince name/id kesinleşecek; şimdilik label+select kombinasyonu.
        """
        log.info(f"Sembol seçiliyor: {symbol}")

        # Sayfanın yüklenmesini bekle
        time.sleep(1)

        symbol_select = self._find_clickable(
            selectors=[
                # "Hisse Seçiniz" label'ının hemen altındaki select
                (By.XPATH, "//label[contains(text(),'Hisse')]/following-sibling::select"),
                (By.XPATH, "//label[contains(text(),'Hisse')]/following::select[1]"),
                # Genel select selector'ları (HTML'den doğrulanacak)
                (By.CSS_SELECTOR, "select[name*='hisse']"),
                (By.CSS_SELECTOR, "select[name*='Hisse']"),
                (By.CSS_SELECTOR, "select[id*='hisse']"),
                (By.CSS_SELECTOR, "select[id*='Hisse']"),
                # Sayfadaki tek/ilk görünür select
                (By.XPATH, "//select[option[contains(text(),'Seçiniz')]]"),
            ],
            description="Hisse seçim dropdown'u",
        )

        if symbol_select:
            from selenium.webdriver.support.ui import Select as SeleniumSelect
            sel = SeleniumSelect(symbol_select)
            try:
                sel.select_by_value(symbol)
            except Exception:
                try:
                    sel.select_by_visible_text(symbol)
                except Exception:
                    # Partial match: THYAO → "THYAO - Türk Hava..." gibi metinler
                    for opt in sel.options:
                        if symbol.upper() in opt.text.upper():
                            opt.click()
                            break
                    else:
                        take_screenshot(self.driver, f"symbol_not_in_list_{symbol}")
                        raise Exception(f"'{symbol}' dropdown listesinde bulunamadı!")
            time.sleep(1)
            log.info(f"✅ Sembol seçildi: {symbol}")
        else:
            take_screenshot(self.driver, f"symbol_select_not_found_{symbol}")
            raise Exception("Hisse seçim dropdown'u bulunamadı!")

    def _select_side(self, side: OrderSide):
        """
        Alış/Satış ayrımı HİSSE ALIŞ ve HİSSE SATIŞ olarak ayrı sayfalarda.
        Bu metod yalnızca _navigate_to_trade_page'in hangi sayfayı açtığını
        doğrular — yanlış sayfadaysa yönlendirir.
        """
        if side == OrderSide.BUY:
            # Zaten Hisse Alış sayfasındayız, kontrol et
            try:
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located(
                        (By.XPATH, "//*[contains(text(),'HİSSE ALIŞ')]")
                    )
                )
                log.info("✅ HİSSE ALIŞ sayfası doğrulandı.")
            except TimeoutException:
                log.warning("⚠️ HİSSE ALIŞ başlığı bulunamadı, yeniden navigate ediliyor...")
                self._navigate_to_submenu_item("Hisse Alış", "HİSSE ALIŞ")
        else:
            log.info("SATIŞ sayfasına yönlendiriliyor...")
            self._navigate_to_submenu_item("Hisse Satış", "HİSSE SATIŞ")

    def _enter_quantity(self, quantity: int):
        """
        Lot/adet girer.
        HİSSE ALIŞ akışı: sembol seçildikten sonra İLERİ'ye basılır,
        2. adımda lot/fiyat alanları gelir (HTML'den doğrulanacak).
        """
        log.info(f"Miktar giriliyor: {quantity}")
        qty_input = self._find_clickable(
            selectors=[
                (By.CSS_SELECTOR, "input[name*='lot']"),
                (By.CSS_SELECTOR, "input[name*='Lot']"),
                (By.CSS_SELECTOR, "input[name*='miktar']"),
                (By.CSS_SELECTOR, "input[name*='adet']"),
                (By.CSS_SELECTOR, "input[id*='lot']"),
                (By.CSS_SELECTOR, "input[id*='miktar']"),
                (By.XPATH, "//label[contains(text(),'Lot')]/following::input[1]"),
                (By.XPATH, "//label[contains(text(),'Miktar')]/following::input[1]"),
                (By.XPATH, "//label[contains(text(),'Adet')]/following::input[1]"),
            ],
            description="Lot/miktar alanı",
        )
        if qty_input:
            qty_input.clear()
            qty_input.send_keys(str(quantity))
            log.info(f"✅ Miktar girildi: {quantity}")
        else:
            take_screenshot(self.driver, "qty_not_found")
            raise Exception("Lot/miktar giriş alanı bulunamadı!")

    def _enter_price(self, price: float):
        """
        Fiyat girer. KuveytTürk sitenin virgüllü format beklediği bilinmektedir.
        Ör: 320.50 → "320,50" olarak girer.
        """
        log.info(f"Fiyat giriliyor: {price}")
        price_input = self._find_clickable(
            selectors=[
                (By.CSS_SELECTOR, "input[name*='fiyat']"),
                (By.CSS_SELECTOR, "input[name*='Fiyat']"),
                (By.CSS_SELECTOR, "input[name*='price']"),
                (By.CSS_SELECTOR, "input[id*='fiyat']"),
                (By.CSS_SELECTOR, "input[id*='Fiyat']"),
                (By.XPATH, "//label[contains(text(),'Fiyat')]/following::input[1]"),
                (By.XPATH, "//label[contains(text(),'Son Fiyat')]/following::input[1]"),
            ],
            description="Fiyat alanı",
        )
        if price_input:
            price_input.clear()
            price_str = f"{price:.2f}".replace(".", ",")  # 320.50 → "320,50"
            price_input.send_keys(price_str)
            log.info(f"✅ Fiyat girildi: {price_str}")
        else:
            take_screenshot(self.driver, "price_not_found")
            raise Exception("Fiyat giriş alanı bulunamadı!")

    def _submit_order(self):
        """
        İLERİ → ardından gelen onay/gönder butonuna basar.
        HİSSE ALIŞ akışı 2 adımlı:
          Adım 1: Hisse seç → İLERİ
          Adım 2: Lot/fiyat gir → GÖNDER (HTML gelince isim kesinleşecek)
        """
        log.info("İLERİ/GÖNDER butonuna basılıyor...")
        submit_btn = self._find_clickable(
            selectors=[
                # Adım 2 — Gönder
                (By.XPATH, "//input[@type='submit' and contains(@value,'GÖNDER')]"),
                (By.XPATH, "//input[@type='submit' and contains(@value,'Gönder')]"),
                (By.XPATH, "//button[contains(text(),'GÖNDER')]"),
                (By.XPATH, "//button[contains(text(),'Gönder')]"),
                # Adım 1 — İLERİ (sembol seçim ekranında)
                (By.XPATH, "//input[@type='submit' and contains(@value,'İLERİ')]"),
                (By.XPATH, "//input[@type='submit' and contains(@value,'İleri')]"),
                (By.XPATH, "//button[normalize-space()='İLERİ']"),
                (By.XPATH, "//button[normalize-space()='İleri']"),
                (By.CSS_SELECTOR, "input[type='submit']"),
                (By.CSS_SELECTOR, "button[type='submit']"),
            ],
            description="İLERİ / GÖNDER butonu",
        )
        if submit_btn:
            try:
                submit_btn.click()
            except Exception:
                self.driver.execute_script("arguments[0].click();", submit_btn)
            time.sleep(2)
            log.info("✅ Form gönderildi.")
        else:
            take_screenshot(self.driver, "submit_not_found")
            raise Exception("İLERİ/GÖNDER butonu bulunamadı!")

    def _confirm_order(self) -> bool:
        """
        Emir onay ekranı — KuveytTürk genellikle modal veya yeni sayfa açar.
        "Hisse almak istiyorum." mesajı onay niyeti olarak altta görünüyor
        (ekran görüntüsü 4). Asıl onay butonu HTML'den doğrulanacak.
        """
        log.info("Emir onaylanıyor...")
        time.sleep(1.5)

        confirm_btn = self._find_clickable(
            selectors=[
                (By.XPATH, "//input[@type='submit' and contains(@value,'ONAYLA')]"),
                (By.XPATH, "//input[@type='submit' and contains(@value,'Onayla')]"),
                (By.XPATH, "//button[contains(text(),'ONAYLA')]"),
                (By.XPATH, "//button[contains(text(),'Onayla')]"),
                (By.XPATH, "//button[contains(text(),'Evet')]"),
                (By.XPATH, "//button[contains(text(),'Tamam')]"),
                (By.CSS_SELECTOR, ".onay-btn"),
                (By.CSS_SELECTOR, ".confirm-button"),
                (By.CSS_SELECTOR, ".modal .btn-primary"),
            ],
            description="Onay butonu",
            timeout=5,
        )
        if confirm_btn:
            try:
                confirm_btn.click()
            except Exception:
                self.driver.execute_script("arguments[0].click();", confirm_btn)
            time.sleep(2)
            log.info("✅ Emir onaylandı.")

        take_screenshot(self.driver, "order_result")
        return True  # Hata kontrolü HTML'den doğrulanınca eklenecek

    # ──────────────────────────────────────────────────────────
    # Portföy
    # ──────────────────────────────────────────────────────────

    def get_portfolio(self) -> list[PortfolioItem]:
        """
        Portföy bilgilerini çeker.

        PORTFÖYÜM sayfası (ekran görüntüsü 2):
          Yatırım → Hesap İşlemleri → Portföyüm
          Başlık: "PORTFÖYÜM"

          "Bakiye Bilgileri (TL)" bölümü — sıralı satırlar:
            Toplam Hisse Değeri    | 0,00 TL
            Toplam Sukuk Değeri    | 0,00 TL
            Toplam Fon Değeri      | 0,00 TL
            T+2 Cari Bakiye (*)    | 0,00 TL
            T+1 Cari Bakiye(*)     | 0,00 TL
            Toplam Portföy Değeri  | 0,00 TL

          Hisse pozisyonları varsa ayrı bir tabloda listelenecek
          (şu an portföy boş — tablo yapısı HTML'den doğrulanacak).
        """
        log.info("Portföy bilgileri çekiliyor...")
        portfolio = []

        try:
            # ── Portföyüm sayfasına git ───────────────────────
            ok = self._navigate_to_submenu_item("Portföyüm", "PORTFÖYÜM")
            if not ok:
                log.error("Portföyüm sayfasına gidilemedi!")
                return []

            take_screenshot(self.driver, "portfolio")

            # ── Bakiye özeti ──────────────────────────────────
            summary = self._parse_portfolio_summary()
            for k, v in summary.items():
                log.info(f"  {k}: {v}")

            # ── Hisse pozisyonları tablosu ────────────────────
            # Ekran görüntüsünde portföy boş; tablo varsa parse et.
            # Tablo başlıkları HTML'den doğrulanınca güncellenecek.
            rows = self.driver.find_elements(
                By.CSS_SELECTOR,
                # KuveytTürk jQuery/HTML sitesi — olası selector'lar:
                "table.portfoyTablosu tbody tr, "
                "table#portfoyTablosu tbody tr, "
                "table tbody tr.portfoy-satir, "
                "table tbody tr"
            )

            for row in rows:
                cells = row.find_elements(By.TAG_NAME, "td")
                if len(cells) >= 4:
                    try:
                        symbol_text = cells[0].text.strip()
                        # Boş veya başlık satırlarını atla
                        if not symbol_text or symbol_text in (
                            "Hisse", "Sembol", "Kod", "Toplam"
                        ):
                            continue
                        item = PortfolioItem(
                            symbol=symbol_text,
                            quantity=int(
                                cells[1].text.strip()
                                .replace(".", "")
                                .replace(",", "")
                                or "0"
                            ),
                            avg_cost=self._parse_price(cells[2].text),
                            current_price=self._parse_price(cells[3].text),
                            profit_loss=(
                                self._parse_price(cells[4].text)
                                if len(cells) > 4 else 0.0
                            ),
                            profit_loss_pct=(
                                self._parse_price(cells[5].text)
                                if len(cells) > 5 else 0.0
                            ),
                        )
                        portfolio.append(item)
                    except (ValueError, IndexError) as e:
                        log.debug(f"Satır parse edilemedi: {e}")

            log.info(f"Portföyde {len(portfolio)} hisse pozisyonu bulundu.")
            for item in portfolio:
                log.info(
                    f"  {item.symbol}: {item.quantity} adet | "
                    f"Maliyet: {format_price(item.avg_cost)} | "
                    f"Güncel: {format_price(item.current_price)} | "
                    f"K/Z: {format_price(item.profit_loss)} ({item.profit_loss_pct:+.2f}%)"
                )

        except Exception as e:
            take_screenshot(self.driver, "portfolio_error")
            log.error(f"Portföy çekilemedi: {e}")

        return portfolio

    def _parse_portfolio_summary(self) -> dict:
        """
        PORTFÖYÜM sayfasındaki 'Bakiye Bilgileri (TL)' tablosunu parse eder.
        Dönüş: {
          'toplam_hisse': float,
          'toplam_sukuk': float,
          'toplam_fon': float,
          't2_bakiye': float,
          't1_bakiye': float,
          'toplam_portfoy': float,
        }
        """
        result = {
            "toplam_hisse": 0.0,
            "toplam_sukuk": 0.0,
            "toplam_fon": 0.0,
            "t2_bakiye": 0.0,
            "t1_bakiye": 0.0,
            "toplam_portfoy": 0.0,
        }
        try:
            # Etiket-değer çiftlerini JS ile çek (siteye özgü tablo yapısı)
            data = self.driver.execute_script("""
                var rows = document.querySelectorAll(
                    'table tr, .bakiyeBilgileri tr, .portfoy-ozet tr'
                );
                var result = {};
                for (var i = 0; i < rows.length; i++) {
                    var cells = rows[i].querySelectorAll('td');
                    if (cells.length >= 2) {
                        var label = (cells[0].textContent || '').trim();
                        var value = (cells[1].textContent || '').trim();
                        if (label) result[label] = value;
                    }
                }
                return result;
            """)
            mapping = {
                "Toplam Hisse Değeri": "toplam_hisse",
                "Toplam Sukuk Değeri": "toplam_sukuk",
                "Toplam Fon Değeri": "toplam_fon",
                "T+2 Cari Bakiye": "t2_bakiye",
                "T+1 Cari Bakiye": "t1_bakiye",
                "Toplam Portföy Değeri": "toplam_portfoy",
            }
            for label, key in mapping.items():
                for raw_label, raw_val in (data or {}).items():
                    if label.lower() in raw_label.lower():
                        result[key] = self._parse_price(raw_val)
                        break
        except Exception as e:
            log.warning(f"Bakiye özeti parse hatası: {e}")
        return result

    def get_portfolio_summary_text(self) -> str:
        """
        Telegram mesajı için portföy özetini düz metin olarak döndürür.
        """
        summary = {}
        try:
            self._navigate_to_submenu_item("Portföyüm", "PORTFÖYÜM")
            summary = self._parse_portfolio_summary()
            items = self.get_portfolio()
        except Exception as e:
            return f"❌ Portföy çekilemedi: {e}"

        lines = [
            "📊 <b>PORTFÖYÜM</b>",
            "",
            f"Toplam Hisse    : <b>{format_price(summary.get('toplam_hisse', 0))}</b>",
            f"Toplam Sukuk    : {format_price(summary.get('toplam_sukuk', 0))}",
            f"Toplam Fon      : {format_price(summary.get('toplam_fon', 0))}",
            f"T+2 Bakiye      : {format_price(summary.get('t2_bakiye', 0))}",
            f"T+1 Bakiye      : {format_price(summary.get('t1_bakiye', 0))}",
            f"Toplam Portföy  : <b>{format_price(summary.get('toplam_portfoy', 0))}</b>",
        ]

        if items:
            lines += ["", "📈 <b>Pozisyonlar:</b>"]
            for it in items:
                pl_sign = "+" if it.profit_loss >= 0 else ""
                lines.append(
                    f"  {it.symbol}: {format_quantity(it.quantity)} lot | "
                    f"Maliyet {format_price(it.avg_cost)} | "
                    f"Güncel {format_price(it.current_price)} | "
                    f"K/Z {pl_sign}{format_price(it.profit_loss)} ({pl_sign}{it.profit_loss_pct:.2f}%)"
                )
        else:
            lines.append("\nPortföyde hisse pozisyonu bulunmuyor.")

        return "\n".join(lines)

    # ──────────────────────────────────────────────────────────
    # Keşif yardımcıları (HTML doğrulama için)
    # ──────────────────────────────────────────────────────────

    def explore_hisse_alis_page(self) -> dict:
        """
        Hisse Alış sayfasına gidip tüm form elemanlarını loglar.
        HTML atıldıktan sonra selector'ları kesinleştirmek için kullanılır.
        """
        log.info("=" * 60)
        log.info("🔍 HİSSE ALIŞ sayfası keşfi başlıyor...")
        log.info("=" * 60)

        self._navigate_to_submenu_item("Hisse Alış", "HİSSE ALIŞ")
        take_screenshot(self.driver, "hisse_alis_explore")

        page_info = {
            "url": self.driver.current_url,
            "title": self.driver.title,
            "inputs": [], "selects": [], "buttons": [], "tables": [],
        }

        # Input'lar
        for i, el in enumerate(self.driver.find_elements(By.TAG_NAME, "input")):
            try:
                info = {
                    "i": i, "type": el.get_attribute("type"),
                    "id": el.get_attribute("id"), "name": el.get_attribute("name"),
                    "value": el.get_attribute("value"),
                    "placeholder": el.get_attribute("placeholder"),
                    "class": (el.get_attribute("class") or "")[:60],
                    "visible": el.is_displayed(),
                }
                page_info["inputs"].append(info)
                if info["visible"]:
                    log.info(f"  INPUT[{i}]: {info}")
            except Exception:
                pass

        # Select'ler
        for i, el in enumerate(self.driver.find_elements(By.TAG_NAME, "select")):
            try:
                from selenium.webdriver.support.ui import Select as SeleniumSelect
                sel = SeleniumSelect(el)
                opts = [o.text.strip() for o in sel.options[:10]]
                info = {
                    "i": i, "id": el.get_attribute("id"),
                    "name": el.get_attribute("name"),
                    "class": (el.get_attribute("class") or "")[:60],
                    "visible": el.is_displayed(),
                    "options_preview": opts,
                }
                page_info["selects"].append(info)
                if info["visible"]:
                    log.info(f"  SELECT[{i}]: {info}")
            except Exception:
                pass

        # Butonlar / submit input'lar
        for i, el in enumerate(
            self.driver.find_elements(
                By.CSS_SELECTOR, "button, input[type='submit'], input[type='button']"
            )
        ):
            try:
                info = {
                    "i": i, "tag": el.tag_name,
                    "type": el.get_attribute("type"),
                    "id": el.get_attribute("id"),
                    "name": el.get_attribute("name"),
                    "value": el.get_attribute("value"),
                    "text": (el.text or "")[:50],
                    "visible": el.is_displayed(),
                }
                page_info["buttons"].append(info)
                if info["visible"]:
                    log.info(f"  BTN[{i}]: {info}")
            except Exception:
                pass

        # Tablolar
        for i, tbl in enumerate(self.driver.find_elements(By.TAG_NAME, "table")):
            try:
                headers = [th.text for th in tbl.find_elements(By.TAG_NAME, "th")]
                row_count = len(tbl.find_elements(By.TAG_NAME, "tr"))
                info = {"i": i, "headers": headers, "rows": row_count,
                        "id": tbl.get_attribute("id"),
                        "class": (tbl.get_attribute("class") or "")[:60]}
                page_info["tables"].append(info)
                log.info(f"  TABLE[{i}]: {info}")
            except Exception:
                pass

        log.info("=" * 60)
        log.info(
            f"📊 Özet: {len(page_info['inputs'])} input, "
            f"{len(page_info['selects'])} select, "
            f"{len(page_info['buttons'])} buton, "
            f"{len(page_info['tables'])} tablo"
        )
        log.info("=" * 60)
        return page_info

    # ──────────────────────────────────────────────────────────
    # Yardımcılar
    # ──────────────────────────────────────────────────────────

    def _find_clickable(self, selectors: list, description: str, timeout: int = 5):
        """Element bulur (tıklanabilir olana kadar bekler)."""
        for by, value in selectors:
            try:
                element = WebDriverWait(self.driver, timeout).until(
                    EC.element_to_be_clickable((by, value))
                )
                log.debug(f"{description} bulundu: {by}={value}")
                return element
            except TimeoutException:
                continue
        log.warning(f"{description} bulunamadı!")
        return None

    def _parse_price(self, text: str) -> float:
        """TradePlus fiyat formatını parse eder. Örn: '320,50' -> 320.50"""
        try:
            cleaned = text.strip().replace(".", "").replace(",", ".").replace(" TL", "").replace("%", "")
            return float(cleaned)
        except (ValueError, AttributeError):
            return 0.0
