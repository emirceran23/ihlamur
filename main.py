#!/usr/bin/env python3
"""
İhlamur - KuveytTürk İnternet Şubesi Otomasyon Botu
Ana giriş noktası.
"""

import argparse
import sys
from core.browser import Browser
from core.auth import Auth
from core.trader import Trader, Order, OrderSide, OrderType
from utils.logger import get_logger
from utils.helpers import send_telegram_message

log = get_logger("ihlamur")


def parse_args():
    parser = argparse.ArgumentParser(
        description="İhlamur - KuveytTürk İnternet Şubesi Otomasyon Botu"
    )
    parser.add_argument(
        "--action",
        choices=["buy", "sell", "portfolio", "explore", "login-test"],
        default="login-test",
        help="Yapılacak işlem (varsayılan: login-test)",
    )
    parser.add_argument("--symbol", type=str, help="Hisse sembolü (ör: THYAO)")
    parser.add_argument("--quantity", type=int, help="Adet")
    parser.add_argument("--price", type=float, help="Fiyat (TL)")
    parser.add_argument(
        "--order-type",
        choices=["limit", "market"],
        default="limit",
        help="Emir tipi",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    log.info("=" * 60)
    log.info("🌳 İhlamur Bot başlatılıyor...")
    log.info(f"   Aksiyon: {args.action}")
    log.info("=" * 60)

    with Browser() as browser:
        driver = browser.driver
        auth = Auth(driver)
        trader = Trader(driver)

        # ── Keşif Modu ────────────────────────────────────────
        if args.action == "explore":
            log.info("Keşif modu: İnternet Şubesi sayfa yapısı inceleniyor...")
            from config.settings import KUVEYTTURK_URL
            import time

            driver.get(KUVEYTTURK_URL)
            log.info("Sayfa yükleniyor, 8 saniye bekleniyor...")
            time.sleep(8)

            log.info(f"URL: {driver.current_url}")
            log.info(f"Title: {driver.title}")

            page_info = auth.explore_page()
            log.info("Keşif tamamlandı.")
            return

        # ── Giriş ─────────────────────────────────────────────
        try:
            auth.login()
        except Exception as e:
            log.error(f"Giriş yapılamadı: {e}")
            send_telegram_message(f"❌ İnternet Şubesi girişi başarısız: {e}")
            sys.exit(1)

        # ── Giriş Testi ───────────────────────────────────────
        if args.action == "login-test":
            log.info("✅ Giriş testi başarılı!")
            send_telegram_message("✅ İnternet Şubesi giriş testi başarılı!")
            auth.logout()
            return

        # ── Portföy ───────────────────────────────────────────
        if args.action == "portfolio":
            portfolio = trader.get_portfolio()
            if portfolio:
                msg = "📊 <b>Portföy Durumu:</b>\n"
                for item in portfolio:
                    emoji = "🟢" if item.profit_loss >= 0 else "🔴"
                    msg += (
                        f"\n{emoji} <b>{item.symbol}</b>: {item.quantity} adet\n"
                        f"   Maliyet: {item.avg_cost:.2f} TL | Güncel: {item.current_price:.2f} TL\n"
                        f"   K/Z: {item.profit_loss:+.2f} TL ({item.profit_loss_pct:+.2f}%)\n"
                    )
                send_telegram_message(msg)
            auth.logout()
            return

        # ── Alış / Satış ──────────────────────────────────────
        if args.action in ("buy", "sell"):
            if not args.symbol:
                log.error("Sembol belirtilmedi! --symbol THYAO")
                sys.exit(1)
            if not args.quantity:
                log.error("Adet belirtilmedi! --quantity 10")
                sys.exit(1)

            order = Order(
                symbol=args.symbol.upper(),
                side=OrderSide.BUY if args.action == "buy" else OrderSide.SELL,
                quantity=args.quantity,
                price=args.price,
                order_type=OrderType.LIMIT if args.order_type == "limit" else OrderType.MARKET,
            )

            log.info(f"Emir hazırlandı: {order}")

            # Kullanıcıya onay
            if args.price:
                total = order.total_value()
                log.info(f"Toplam tutar: {total:,.2f} TL")

            success = trader.place_order(order)

            if success:
                log.info("✅ İşlem tamamlandı!")
            else:
                log.error("❌ İşlem başarısız!")

            auth.logout()
            return

    log.info("🌳 İhlamur Bot kapatıldı.")


if __name__ == "__main__":
    main()
