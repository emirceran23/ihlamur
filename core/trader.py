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
    # Menü Navigasyonu  (keşif 2026-03-19)
    # ──────────────────────────────────────────────────────────

    # Sayfa URL haritası — deepscan + HTML incelemesiyle doğrulandı
    PAGE_URLS = {
        "hisse_alis":    "/StockBuy/Index/1446",
        "hisse_satis":   "/StockSell/Index/1447",
        "emirlerim":     "/StockOrder/Index/1448",
        "hisse_hareketleri": "/StockMovement/Index/1449",
        "portfoy":       "/Portfolio/Index/1451",
        "yatirim_hesaplari": "/InvestmentAccount/Index/1450",
        "fon_alis":      "/FundBuy/Index/1443",
        "fon_satis":     "/FundSell/Index/1444",
        "emir_takip":    "/FundOrder/Index/1445",
    }
    BASE_URL = "https://isube.kuveytturk.com.tr"

    def navigate_to_page(self, page_key: str, title_keyword: str) -> bool:
        """
        Sayfa URL'sine doğrudan gider (AJAX menü bypass).
        page_key: PAGE_URLS sözlüğündeki anahtar.

        KuveytTürk sayfaları cookie oturumu gerektirir;
        oturum açıksa driver.get() ile direkt açılır.
        Fallback: URL çalışmazsa link text ile menüden gitmeyi dener.
        """
        path = self.PAGE_URLS.get(page_key)
        if not path:
            log.error(f"Bilinmeyen sayfa anahtarı: {page_key}")
            return False

        url = self.BASE_URL + path
        log.info(f"Sayfaya gidiliyor: {url}")
        self.driver.get(url)
        time.sleep(3)

        # Başlık kontrolü
        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(
                    (By.XPATH, f"//*[contains(text(), '{title_keyword}')]")
                )
            )
            log.info(f"✅ Sayfa yüklendi: {self.driver.current_url}")
            return True
        except TimeoutException:
            log.warning(
                f"⚠️ '{title_keyword}' başlığı bulunamadı. "
                f"URL: {self.driver.current_url} — menü üzerinden deneniyor..."
            )
            take_screenshot(self.driver, f"direct_url_failed_{page_key}")
            # Fallback: menü üzerinden git
            return self._navigate_via_menu(page_key, title_keyword)

    def _navigate_via_menu(self, page_key: str, title_keyword: str) -> bool:
        """
        URL ile açılamazsa Yatırım menüsüne gidip link text ile tıklar.
        Menü linkleri deepscan ile doğrulandı (2026-03-19):
          "Hisse Alış", "Hisse Satış", "Portföyüm", "Yatırım Hesapları", vb.
        """
        menu_labels = {
            "hisse_alis":        "Hisse Alış",
            "hisse_satis":       "Hisse Satış",
            "emirlerim":         "Emirlerim",
            "hisse_hareketleri": "Hisse Hareketleri",
            "portfoy":           "Portföyüm",
            "yatirim_hesaplari": "Yatırım Hesapları",
            "fon_alis":          "Fon Alış",
            "fon_satis":         "Fon Satış",
            "emir_takip":        "Emir Takip",
        }
        label = menu_labels.get(page_key)
        if not label:
            return False
        return self._navigate_to_submenu_item(label, title_keyword)

    def navigate_to_investment_menu(self) -> bool:
        """
        Ana menüden 'Yatırım' linkine tıklar → alt menü açılır.
        Keşif (2026-03-19): LINK_TEXT "Yatırım" çalışıyor.
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
        Yatırım alt menüsündeki bir linke tıklar.
        deepscan ile doğrulandı: alt menü linkleri display:none değil,
        sadece rect=0 olabiliyorlar → JS click gerekiyor.
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
            # ── Adım 1: İşlem sayfasına git (alış/satış sayfasını direkt aç) ──
            self._navigate_to_trade_page(order.side)

            # ── Adım 2: Alış/Satış sayfa doğrulaması ─────────
            self._select_side(order.side)

            # ── Adım 3: Hisse sembolünü gir ──────────────────
            self._enter_symbol(order.symbol)

            # ── Adım 4: İLERİ — sembol onayı ─────────────────
            self._submit_order()

            # ── Adım 5: 2. ekran — lot/fiyat formu ───────────
            # İLERİ sonrası yeni form yükleniyor — bekle
            time.sleep(2)

            # ── Adım 6: Miktarı gir ──────────────────────────
            self._enter_quantity(order.quantity)

            # ── Adım 7: Fiyatı gir (limit emir ise) ──────────
            if order.order_type == OrderType.LIMIT and order.price:
                self._enter_price(order.price)

            # ── Adım 8: GÖNDER ───────────────────────────────
            self._submit_order()

            # ── Adım 9: Onay ─────────────────────────────────
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

    def _navigate_to_trade_page(self, side: "OrderSide | None" = None):
        """
        Hisse Alış veya Hisse Satış sayfasına gider.
        side=BUY (varsayılan) → Hisse Alış
        side=SELL             → Hisse Satış
        Yol (keşif 2026-03-19): Yatırım menüsü → tıkla "Hisse Alış/Satış"
        URL Main#_ kalır — AJAX ile yüklenir.
        """
        if side is not None and side == OrderSide.SELL:
            log.info("Hisse Satış sayfasına gidiliyor...")
            self._navigate_to_submenu_item("Hisse Satış", "HİSSE SATIŞ")
        else:
            log.info("Hisse Alış sayfasına gidiliyor...")
            self._navigate_to_submenu_item("Hisse Alış", "HİSSE ALIŞ")

    def _enter_symbol(self, symbol: str):
        """
        Hisse sembolünü seçer.

        Keşif (2026-03-19) — DOM yapısı (inspect):
          KuveytTürk custom selectbox widget:
            <div class="dropdown_container" for="SelectedStockCode">
              <input id="SelectedStockCode_input"     readonly class="selectbox back">
              <input id="SelectedStockCode_textinput"  readonly class="selectbox text" style="width:190px">
              <div   id="SelectedStockCode_container"  class="selectbox-wrapper" style="display:none; width:225px">
                ... liste öğeleri (tıklanınca seçim yapılır) ...
              </div>
              <select id="SelectedStockCode" name="SelectedStockCode" style="display:none">
                <option>-- Seçiniz --</option>
                <option>ALBRK-E</option>
                ...
              </select>
            </div>

          Önemli: <select> gizli (display:none)!
          Widget akışı:
            1. _textinput'a tıkla → _container açılır (display:block)
            2. _container içindeki öğeye tıkla → widget seçimi yapar, AJAX tetiklenir
            3. Gizli <select>'e programatik değer yazınca site algılamıyor

        Strateji:
          Yol 1: _textinput'a tıkla → _container'dan öğeyi bul ve tıkla
          Yol 2: JS ile widget mekanizmasını simüle et (gizli select + visible input + event)
        """
        log.info(f"Sembol giriliyor: {symbol}")
        time.sleep(0.5)
        symbol_upper = symbol.upper().strip()

        # ── Yol 1: Custom selectbox widget — tıklama ile seçim ──
        try:
            textinput = self.driver.find_element(By.ID, "SelectedStockCode_textinput")
            log.info("  Custom selectbox widget bulundu (SelectedStockCode_textinput)")

            # Scroll + tıkla → dropdown container açılır
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'}); arguments[0].click();",
                textinput,
            )
            log.info("  _textinput'a tıklandı, container açılması bekleniyor...")
            time.sleep(1)

            # Container'ı bul
            container = None
            for sel in [
                "SelectedStockCode_container",
                "SelectedStockCode_listbox",
            ]:
                try:
                    c = self.driver.find_element(By.ID, sel)
                    if c.is_displayed():
                        container = c
                        log.info(f"  Container açıldı: #{sel}")
                        break
                except Exception:
                    continue

            # Container bulunamazsa veya görünür değilse, JS ile açmayı dene
            if not container:
                log.info("  Container görünür değil, JS ile açma deneniyor...")
                self.driver.execute_script("""
                    var c = document.getElementById('SelectedStockCode_container');
                    if (c) { c.style.display = 'block'; }
                """)
                time.sleep(0.5)
                try:
                    container = self.driver.find_element(By.ID, "SelectedStockCode_container")
                except Exception:
                    container = None

            if container:
                # Container içindeki tüm tıklanabilir öğeleri bul
                items = container.find_elements(By.CSS_SELECTOR, "div, li, a, span")
                log.info(f"  Container'da {len(items)} öğe bulundu")

                # Eşleşen öğeyi bul
                target_item = None
                for item in items:
                    item_text = item.text.strip().upper()
                    item_val = (item.get_attribute("value") or "").upper()
                    item_data = (item.get_attribute("data-value") or "").upper()
                    all_text = f"{item_text} {item_val} {item_data}"
                    if symbol_upper in all_text:
                        if len(item_text) < 2 and len(item_val) < 2 and len(item_data) < 2:
                            continue
                        target_item = item
                        if item_text.startswith(symbol_upper) or item_val.startswith(symbol_upper):
                            break

                if target_item:
                    target_text = target_item.text.strip() or target_item.get_attribute("value") or "?"
                    log.info(f"  Eşleşen öğe bulundu: '{target_text}'")
                    try:
                        self.driver.execute_script(
                            "arguments[0].scrollIntoView({block:'center'});",
                            target_item,
                        )
                        target_item.click()
                    except Exception:
                        self.driver.execute_script("arguments[0].click();", target_item)

                    log.info(f"✅ Hisse seçildi (tıklama): {target_text}")
                    time.sleep(3)
                    take_screenshot(self.driver, f"symbol_selected_{symbol}")
                    return
                else:
                    all_texts = []
                    for item in items[:30]:
                        t = item.text.strip()
                        if t and t not in all_texts:
                            all_texts.append(t)
                    log.warning(f"  '{symbol}' container'da bulunamadı! "
                                f"Mevcut öğeler: {all_texts[:15]}")

        except Exception as e:
            log.warning(f"  Custom selectbox yolu başarısız: {e}")

        # ── Yol 2: JS ile gizli <select>'ten seç + widget'ı güncelle ──
        log.info("  Yol 2: JS ile gizli <select> + _textinput güncelle...")
        try:
            result = self.driver.execute_script("""
                var symbol = arguments[0];
                var sel = document.getElementById('SelectedStockCode');
                if (!sel) return { error: 'select bulunamadı' };

                var target = null;
                for (var i = 0; i < sel.options.length; i++) {
                    var t = sel.options[i].text.trim().toUpperCase();
                    var v = sel.options[i].value.toUpperCase();
                    if (t.indexOf(symbol) === 0 || v.indexOf(symbol) === 0) {
                        target = { index: i, text: sel.options[i].text.trim(), value: sel.options[i].value };
                        break;
                    }
                }
                if (!target) {
                    for (var i = 0; i < sel.options.length; i++) {
                        var t = sel.options[i].text.trim().toUpperCase();
                        if (t.indexOf(symbol) >= 0) {
                            target = { index: i, text: sel.options[i].text.trim(), value: sel.options[i].value };
                            break;
                        }
                    }
                }
                if (!target) {
                    var opts = [];
                    for (var i = 0; i < Math.min(sel.options.length, 15); i++) {
                        opts.push(sel.options[i].text.trim());
                    }
                    return { error: 'bulunamadı', options: opts };
                }

                // 1. Gizli <select>'i ayarla
                sel.selectedIndex = target.index;
                sel.value = target.value;

                // 2. _textinput ve _input'u güncelle (widget'ın görünen kısımları)
                var ti = document.getElementById('SelectedStockCode_textinput');
                var bi = document.getElementById('SelectedStockCode_input');
                if (ti) { ti.value = target.text; }
                if (bi) { bi.value = target.value; }

                // 3. Tüm event'leri tetikle
                var els = [sel, ti, bi].filter(function(e) { return !!e; });
                ['focus', 'change', 'input', 'blur'].forEach(function(evt) {
                    els.forEach(function(el) {
                        el.dispatchEvent(new Event(evt, { bubbles: true }));
                    });
                });

                // 4. jQuery trigger
                if (typeof jQuery !== 'undefined') {
                    jQuery(sel).val(target.value).trigger('change');
                    if (ti) jQuery(ti).trigger('change').trigger('blur');
                    if (bi) jQuery(bi).trigger('change').trigger('blur');
                    jQuery('#SelectedStockCode_container').hide();
                }

                return { ok: true, text: target.text, value: target.value };
            """, symbol_upper)

            if isinstance(result, dict):
                if result.get("error"):
                    take_screenshot(self.driver, f"symbol_not_found_{symbol}")
                    raise Exception(
                        f"'{symbol}' dropdown'da bulunamadı! "
                        f"Mevcut: {result.get('options', [])}"
                    )
                log.info(f"✅ Hisse seçildi (JS fallback): {result.get('text')} "
                          f"(value={result.get('value')})")
            else:
                log.warning(f"  JS sonucu beklenmeyen: {result}")

        except Exception as e:
            if "bulunamadı" in str(e) or "dropdown" in str(e):
                raise
            log.error(f"  JS fallback hatası: {e}")
            take_screenshot(self.driver, f"symbol_error_{symbol}")
            raise

        time.sleep(3)
        take_screenshot(self.driver, f"symbol_selected_{symbol}")


    def _select_side(self, side: OrderSide):
        """
        Alış/Satış ayrımı HİSSE ALIŞ ve HİSSE SATIŞ olarak ayrı sayfalarda.
        BUY: _navigate_to_trade_page() zaten Hisse Alış sayfasını açtı — sadece doğrula.
        SELL: Hisse Satış sayfasına git.
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
        İLERİ butonuna basar.

        Keşif (2026-03-19):
          - deepscan çıktısında buton text = "İLERİ"
          - Hisse seçilince fiyat tablosu yükleniyor, sayfa uzuyor
          - İLERİ butonu ekran dışında kalabiliyor → scroll + JS click
          Adım 1 (sembol seçimi) → İLERİ → Adım 2 (lot/fiyat)
          Adım 2 (lot/fiyat dolu) → İLERİ (veya GÖNDER) → onay
        """
        log.info("İLERİ butonuna basılıyor...")
        ileri_btn = self._find_clickable(
            selectors=[
                (By.XPATH, "//input[@type='submit' and contains(@value,'İLERİ')]"),
                (By.XPATH, "//input[@type='submit' and contains(@value,'ILERI')]"),
                (By.XPATH, "//button[normalize-space()='İLERİ']"),
                (By.XPATH, "//button[normalize-space()='ILERI']"),
                (By.XPATH, "//input[@type='button' and contains(@value,'İLERİ')]"),
                # 2. adım — Gönder butonu (form submit)
                (By.XPATH, "//input[@type='submit' and contains(@value,'GÖNDER')]"),
                (By.XPATH, "//button[normalize-space()='GÖNDER']"),
                (By.CSS_SELECTOR, "input[type='submit']"),
                (By.CSS_SELECTOR, "button[type='submit']"),
            ],
            description="İLERİ butonu",
            timeout=8,
        )
        if ileri_btn:
            # Buton ekran dışında olabilir — scroll into view + JS click
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'}); "
                "arguments[0].focus();",
                ileri_btn,
            )
            time.sleep(0.5)
            try:
                ileri_btn.click()
            except Exception:
                self.driver.execute_script("arguments[0].click();", ileri_btn)
            log.info(f"✅ Buton tıklandı: {ileri_btn.get_attribute('value') or ileri_btn.text}")
            time.sleep(2)
        else:
            take_screenshot(self.driver, "ileri_not_found")
            raise Exception("İLERİ butonu bulunamadı!")

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
            ok = self.navigate_to_page("portfoy", "PORTFÖYÜM")
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

        self.navigate_to_page("hisse_alis", "HİSSE ALIŞ")
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
