"""
KuveytTürk TradePlus İşlem modülü.
Hisse alım, satım ve portföy sorgulama işlemleri.
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
        """İşlem sayfasına gider."""
        log.info("İşlem sayfasına gidiliyor...")
        # TradePlus'ta işlem sayfası navigasyonu
        # Selector'lar keşif sonrası güncellenecek
        trade_menu = self._find_clickable(
            selectors=[
                (By.XPATH, "//a[contains(text(), 'Emir')]"),
                (By.XPATH, "//a[contains(text(), 'İşlem')]"),
                (By.XPATH, "//*[contains(text(), 'Hisse')]"),
                (By.CSS_SELECTOR, "[data-menu='trade']"),
                (By.CSS_SELECTOR, ".trade-menu"),
            ],
            description="İşlem menüsü",
        )
        if trade_menu:
            trade_menu.click()
            time.sleep(2)

    def _enter_symbol(self, symbol: str):
        """Hisse sembolünü girer."""
        log.info(f"Sembol giriliyor: {symbol}")
        symbol_input = self._find_clickable(
            selectors=[
                (By.CSS_SELECTOR, "input[placeholder*='Sembol']"),
                (By.CSS_SELECTOR, "input[placeholder*='sembol']"),
                (By.CSS_SELECTOR, "input[placeholder*='Hisse']"),
                (By.CSS_SELECTOR, "input[placeholder*='Ara']"),
                (By.CSS_SELECTOR, ".symbol-search input"),
                (By.ID, "symbol"),
                (By.NAME, "symbol"),
            ],
            description="Sembol arama kutusu",
        )
        if symbol_input:
            symbol_input.clear()
            symbol_input.send_keys(symbol)
            time.sleep(1)
            # Otomatik tamamlama listesinden seç
            symbol_input.send_keys(Keys.ENTER)
            time.sleep(1)
        else:
            take_screenshot(self.driver, f"symbol_not_found_{symbol}")
            raise Exception(f"Sembol giriş alanı bulunamadı: {symbol}")

    def _select_side(self, side: OrderSide):
        """Alış veya satış seçer."""
        if side == OrderSide.BUY:
            log.info("ALIŞ seçiliyor...")
            btn = self._find_clickable(
                selectors=[
                    (By.XPATH, "//button[contains(text(), 'Alış')]"),
                    (By.XPATH, "//button[contains(text(), 'ALIŞ')]"),
                    (By.XPATH, "//*[contains(text(), 'AL')]"),
                    (By.CSS_SELECTOR, ".buy-button"),
                    (By.CSS_SELECTOR, "[data-side='buy']"),
                ],
                description="Alış butonu",
            )
        else:
            log.info("SATIŞ seçiliyor...")
            btn = self._find_clickable(
                selectors=[
                    (By.XPATH, "//button[contains(text(), 'Satış')]"),
                    (By.XPATH, "//button[contains(text(), 'SATIŞ')]"),
                    (By.XPATH, "//*[contains(text(), 'SAT')]"),
                    (By.CSS_SELECTOR, ".sell-button"),
                    (By.CSS_SELECTOR, "[data-side='sell']"),
                ],
                description="Satış butonu",
            )

        if btn:
            btn.click()
            time.sleep(0.5)
        else:
            raise Exception(f"{'Alış' if side == OrderSide.BUY else 'Satış'} butonu bulunamadı!")

    def _enter_quantity(self, quantity: int):
        """Adet girer."""
        log.info(f"Miktar giriliyor: {quantity}")
        qty_input = self._find_clickable(
            selectors=[
                (By.CSS_SELECTOR, "input[placeholder*='Miktar']"),
                (By.CSS_SELECTOR, "input[placeholder*='Adet']"),
                (By.CSS_SELECTOR, "input[placeholder*='miktar']"),
                (By.CSS_SELECTOR, "input[placeholder*='adet']"),
                (By.ID, "quantity"),
                (By.NAME, "quantity"),
                (By.NAME, "lot"),
            ],
            description="Miktar alanı",
        )
        if qty_input:
            qty_input.clear()
            qty_input.send_keys(str(quantity))
        else:
            raise Exception("Miktar giriş alanı bulunamadı!")

    def _enter_price(self, price: float):
        """Fiyat girer."""
        log.info(f"Fiyat giriliyor: {price}")
        price_input = self._find_clickable(
            selectors=[
                (By.CSS_SELECTOR, "input[placeholder*='Fiyat']"),
                (By.CSS_SELECTOR, "input[placeholder*='fiyat']"),
                (By.ID, "price"),
                (By.NAME, "price"),
                (By.NAME, "fiyat"),
            ],
            description="Fiyat alanı",
        )
        if price_input:
            price_input.clear()
            # TradePlus virgüllü fiyat bekleyebilir
            price_str = str(price).replace(".", ",")
            price_input.send_keys(price_str)
        else:
            raise Exception("Fiyat giriş alanı bulunamadı!")

    def _submit_order(self):
        """Emri gönderir."""
        log.info("Emir gönderiliyor...")
        submit_btn = self._find_clickable(
            selectors=[
                (By.XPATH, "//button[contains(text(), 'Gönder')]"),
                (By.XPATH, "//button[contains(text(), 'GÖNDER')]"),
                (By.XPATH, "//button[contains(text(), 'Emri Gönder')]"),
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.CSS_SELECTOR, ".submit-order"),
                (By.CSS_SELECTOR, ".order-submit"),
            ],
            description="Emir gönder butonu",
        )
        if submit_btn:
            submit_btn.click()
            time.sleep(2)
        else:
            take_screenshot(self.driver, "submit_not_found")
            raise Exception("Emir gönder butonu bulunamadı!")

    def _confirm_order(self) -> bool:
        """Emir onay diyaloğunu onaylar."""
        log.info("Emir onaylanıyor...")
        time.sleep(1)

        # Onay diyaloğu varsa
        confirm_btn = self._find_clickable(
            selectors=[
                (By.XPATH, "//button[contains(text(), 'Onayla')]"),
                (By.XPATH, "//button[contains(text(), 'ONAYLA')]"),
                (By.XPATH, "//button[contains(text(), 'Evet')]"),
                (By.XPATH, "//button[contains(text(), 'Tamam')]"),
                (By.CSS_SELECTOR, ".confirm-button"),
                (By.CSS_SELECTOR, ".modal .btn-primary"),
            ],
            description="Onay butonu",
        )
        if confirm_btn:
            confirm_btn.click()
            time.sleep(2)

        # Başarı mesajı kontrolü
        take_screenshot(self.driver, "order_result")
        return True  # Detaylı kontrol keşif sonrası eklenecek

    # ──────────────────────────────────────────────────────────
    # Portföy
    # ──────────────────────────────────────────────────────────

    def get_portfolio(self) -> list[PortfolioItem]:
        """Portföy bilgilerini çeker."""
        log.info("Portföy bilgileri çekiliyor...")
        portfolio = []

        try:
            # Portföy sayfasına git
            portfolio_menu = self._find_clickable(
                selectors=[
                    (By.XPATH, "//a[contains(text(), 'Portföy')]"),
                    (By.XPATH, "//*[contains(text(), 'Portföy')]"),
                    (By.CSS_SELECTOR, "[data-menu='portfolio']"),
                    (By.CSS_SELECTOR, ".portfolio-menu"),
                ],
                description="Portföy menüsü",
            )
            if portfolio_menu:
                portfolio_menu.click()
                time.sleep(3)

            take_screenshot(self.driver, "portfolio")

            # Portföy tablosunu parse et
            # Selector'lar keşif sonrası güncellenecek
            rows = self.driver.find_elements(
                By.CSS_SELECTOR, "table tbody tr, .portfolio-row"
            )

            for row in rows:
                cells = row.find_elements(By.TAG_NAME, "td")
                if len(cells) >= 4:
                    try:
                        item = PortfolioItem(
                            symbol=cells[0].text.strip(),
                            quantity=int(cells[1].text.strip().replace(".", "")),
                            avg_cost=self._parse_price(cells[2].text),
                            current_price=self._parse_price(cells[3].text),
                            profit_loss=self._parse_price(cells[4].text) if len(cells) > 4 else 0.0,
                            profit_loss_pct=self._parse_price(cells[5].text) if len(cells) > 5 else 0.0,
                        )
                        portfolio.append(item)
                    except (ValueError, IndexError) as e:
                        log.debug(f"Satır parse edilemedi: {e}")

            log.info(f"Portföyde {len(portfolio)} hisse bulundu.")
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

    # ──────────────────────────────────────────────────────────
    # Keşif (İlk kurulum için)
    # ──────────────────────────────────────────────────────────

    def explore_stock_page(self) -> dict:
        """
        Hisse Senedi tabına tıklayıp sayfadaki tüm elementleri keşfeder.
        Bu bilgilerle emir gönderme selector'larını belirleyeceğiz.
        """
        log.info("=" * 60)
        log.info("🔍 Hisse Senedi sayfası keşfi başlıyor...")
        log.info("=" * 60)

        take_screenshot(self.driver, "before_stock_tab")

        # ── Adım 1: "Hisse Senedi" tabına tıkla ─────────────
        stock_tab = self._find_clickable(
            selectors=[
                (By.XPATH, "//button[contains(text(), 'Hisse Senedi')]"),
                (By.XPATH, "//span[contains(text(), 'Hisse Senedi')]/.."),
                (By.XPATH, "//*[contains(@class, 'MuiTab')][contains(text(), 'Hisse')]"),
                (By.CSS_SELECTOR, ".MuiTab-root:nth-child(2)"),
            ],
            description="Hisse Senedi tabı",
        )
        if stock_tab:
            stock_tab.click()
            log.info("✅ Hisse Senedi tabına tıklandı!")
            time.sleep(5)  # Sayfanın yüklenmesini bekle
        else:
            log.warning("⚠️ Hisse Senedi tabı bulunamadı!")

        take_screenshot(self.driver, "stock_tab_clicked")

        # ── Adım 2: Sayfadaki tüm elementleri keşfet ─────────
        page_info = {
            "url": self.driver.current_url,
            "title": self.driver.title,
            "inputs": [],
            "buttons": [],
            "selects": [],
            "tables": [],
            "divs_with_text": [],
            "links": [],
        }

        # Input'lar
        inputs = self.driver.find_elements(By.TAG_NAME, "input")
        for i, inp in enumerate(inputs):
            try:
                info = {
                    "index": i,
                    "type": inp.get_attribute("type"),
                    "id": inp.get_attribute("id"),
                    "name": inp.get_attribute("name"),
                    "placeholder": inp.get_attribute("placeholder"),
                    "class": inp.get_attribute("class"),
                    "value": inp.get_attribute("value"),
                    "visible": inp.is_displayed(),
                    "aria-label": inp.get_attribute("aria-label"),
                }
                page_info["inputs"].append(info)
                if info["visible"]:
                    log.info(f"  Input[{i}]: type={info['type']} | placeholder={info['placeholder']} | id={info['id']} | class={info['class'][:60] if info['class'] else ''}")
            except Exception:
                pass

        # Butonlar
        buttons = self.driver.find_elements(By.TAG_NAME, "button")
        for i, btn in enumerate(buttons):
            try:
                info = {
                    "index": i,
                    "text": btn.text[:80] if btn.text else "",
                    "id": btn.get_attribute("id"),
                    "class": btn.get_attribute("class"),
                    "type": btn.get_attribute("type"),
                    "visible": btn.is_displayed(),
                    "aria-label": btn.get_attribute("aria-label"),
                }
                page_info["buttons"].append(info)
                if info["visible"] and info["text"]:
                    log.info(f"  Buton[{i}]: {info['text']} | class={info['class'][:80] if info['class'] else ''}")
            except Exception:
                pass

        # MuiTab'lar (React tabları)
        tabs = self.driver.find_elements(By.CSS_SELECTOR, "[role='tab']")
        for i, tab in enumerate(tabs):
            try:
                log.info(f"  Tab[{i}]: {tab.text} | selected={tab.get_attribute('aria-selected')} | class={tab.get_attribute('class')[:80]}")
            except Exception:
                pass

        # Tablolar
        tables = self.driver.find_elements(By.TAG_NAME, "table")
        for i, table in enumerate(tables):
            try:
                headers = [th.text for th in table.find_elements(By.TAG_NAME, "th")]
                rows_count = len(table.find_elements(By.TAG_NAME, "tr"))
                log.info(f"  Tablo[{i}]: {rows_count} satır | Başlıklar: {headers}")
                page_info["tables"].append({"headers": headers, "rows": rows_count})
            except Exception:
                pass

        # Önemli div'ler - Alış/Satış/Emir ile ilgili olanlar
        keywords = ["Alış", "Satış", "Emir", "Lot", "Fiyat", "Miktar", "Sembol", "Hisse", "İşlem"]
        for keyword in keywords:
            try:
                elements = self.driver.find_elements(
                    By.XPATH, f"//*[contains(text(), '{keyword}')]"
                )
                for el in elements[:3]:  # her keyword için max 3
                    if el.is_displayed():
                        log.info(f"  BULUNDU: {keyword} -> tag={el.tag_name} text={el.text[:80]} class={el.get_attribute('class')[:60] if el.get_attribute('class') else ''}")
                        page_info["divs_with_text"].append({
                            "keyword": keyword,
                            "tag": el.tag_name,
                            "text": el.text[:80],
                            "class": el.get_attribute("class"),
                        })
            except Exception:
                pass

        # Select (dropdown) elemanları
        selects = self.driver.find_elements(By.TAG_NAME, "select")
        for i, sel in enumerate(selects):
            try:
                log.info(f"  Select[{i}]: id={sel.get_attribute('id')} name={sel.get_attribute('name')}")
                page_info["selects"].append({
                    "id": sel.get_attribute("id"),
                    "name": sel.get_attribute("name"),
                })
            except Exception:
                pass

        # MUI Select'ler (dropdown gibi çalışan div'ler)
        mui_selects = self.driver.find_elements(By.CSS_SELECTOR, "[role='button'][aria-haspopup]")
        for i, ms in enumerate(mui_selects):
            try:
                if ms.is_displayed():
                    log.info(f"  MUI-Select[{i}]: text={ms.text[:50]} class={ms.get_attribute('class')[:60]}")
            except Exception:
                pass

        # Link'ler
        links = self.driver.find_elements(By.TAG_NAME, "a")
        for i, link in enumerate(links):
            try:
                if link.is_displayed() and link.text:
                    href = link.get_attribute("href") or ""
                    log.info(f"  Link[{i}]: {link.text[:50]} -> {href[:80]}")
                    page_info["links"].append({"text": link.text[:50], "href": href[:80]})
            except Exception:
                pass

        log.info("=" * 60)
        log.info(f"📊 Özet: {len(page_info['inputs'])} input, {len(page_info['buttons'])} buton, {len(page_info['tables'])} tablo")
        log.info("=" * 60)

        take_screenshot(self.driver, "stock_page_explored")
        return page_info

    def explore_trade_page(self) -> dict:
        """
        İşlem sayfasının yapısını keşfeder.
        İlk çalıştırmada kullanılır, selector'ları belirlemek için.
        """
        log.info("İşlem sayfası keşfediliyor...")
        take_screenshot(self.driver, "trade_page_explore")

        page_info = {
            "url": self.driver.current_url,
            "title": self.driver.title,
            "inputs": [],
            "buttons": [],
            "selects": [],
            "tables": [],
        }

        for tag, key in [("input", "inputs"), ("button", "buttons"), ("select", "selects")]:
            elements = self.driver.find_elements(By.TAG_NAME, tag)
            for el in elements:
                page_info[key].append({
                    "tag": tag,
                    "text": el.text[:50] if el.text else "",
                    "id": el.get_attribute("id"),
                    "name": el.get_attribute("name"),
                    "class": el.get_attribute("class"),
                    "type": el.get_attribute("type"),
                    "placeholder": el.get_attribute("placeholder"),
                    "visible": el.is_displayed(),
                })

        tables = self.driver.find_elements(By.TAG_NAME, "table")
        for table in tables:
            headers = [th.text for th in table.find_elements(By.TAG_NAME, "th")]
            page_info["tables"].append({"headers": headers})

        # Detaylı log
        for key in ["inputs", "buttons", "selects"]:
            log.info(f"\n{'='*50}")
            log.info(f"{key.upper()} ({len(page_info[key])} adet):")
            for i, item in enumerate(page_info[key]):
                if item.get("visible"):
                    log.info(f"  [{i}] {item}")

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
