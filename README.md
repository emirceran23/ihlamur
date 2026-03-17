# 🌳 İhlamur - KuveytTürk TradePlus Otomasyon Botu

Selenium tabanlı KuveytTürk TradePlus işlem otomasyon sistemi.

## 🏗️ Proje Yapısı

```
ihlamur/
├── config/
│   ├── settings.py          # Genel ayarlar
│   └── credentials.py       # Kimlik bilgileri (template)
├── core/
│   ├── __init__.py
│   ├── browser.py            # Selenium browser yönetimi
│   ├── auth.py               # TradePlus giriş/çıkış
│   └── trader.py             # Alım/Satım işlemleri
├── utils/
│   ├── __init__.py
│   ├── logger.py             # Loglama
│   └── helpers.py            # Yardımcı fonksiyonlar
├── main.py                   # Ana giriş noktası
├── requirements.txt
└── .env.example
```

## 🚀 Kurulum

```bash
# Virtual environment oluştur
python3 -m venv venv
source venv/bin/activate

# Bağımlılıkları kur
pip install -r requirements.txt

# Chrome/Chromium ve ChromeDriver kur (DigitalOcean droplet)
apt-get update && apt-get install -y chromium-browser chromium-chromedriver

# .env dosyasını oluştur
cp .env.example .env
# .env dosyasını düzenle ve bilgilerini gir
```

## ⚙️ Kullanım

```bash
# Botu başlat
python main.py

# Belirli bir komutla başlat
python main.py --action buy --symbol THYAO --quantity 10 --price 320.50
python main.py --action sell --symbol THYAO --quantity 10 --price 325.00
python main.py --action portfolio
```

## 📋 Aşamalar

- [x] Aşama 1: Selenium ile TradePlus girişi ve işlem altyapısı
- [ ] Aşama 2: Piyasa analizi entegrasyonu
- [ ] Aşama 3: X (Twitter) platformundan veri çekme
- [ ] Aşama 4: OpenClaw / Telegram bot entegrasyonu
- [ ] Aşama 5: Strateji motoru

## ⚠️ Uyarı

Bu bot kişisel kullanım amaçlıdır. Otomatik işlem riskleri tamamen kullanıcıya aittir.
