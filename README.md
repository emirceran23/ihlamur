# 🌳 İhlamur - KuveytTürk İnternet Şubesi Otomasyon Botu

Selenium tabanlı KuveytTürk İnternet Şubesi otomasyon sistemi.  
Telegram üzerinden tamamen uzaktan yönetilebilir.

---

## 📋 Durum Özeti

| Bileşen | Durum | Notlar |
|---------|-------|--------|
| KuveytTürk girişi | ✅ Tamamlandı | CAPTCHA + mobil onay dahil |
| Cookie/session yönetimi | ✅ Tamamlandı | 30 dk'da bir yenilenir |
| Telegram komut botu | ✅ Tamamlandı | 7 komut |
| Explore (uzaktan kumanda) | ✅ Tamamlandı | Tıkla/yaz/scroll/JS |
| Hisse senedi alım/satım | ⬜ Yapılacak | Dashboard keşfi bekleniyor |
| Strateji motoru | ⬜ Yapılacak | — |

---

## 🏗️ Proje Yapısı

```
ihlamur/
├── config/
│   └── settings.py           # Tüm ayarlar ve env değişkenleri
├── core/
│   ├── auth.py               # KuveytTürk İnternet Şubesi giriş/çıkış
│   ├── browser.py            # Selenium headless Chrome yönetimi
│   ├── session.py            # Cookie kaydet/yükle, keep-alive
│   ├── telegram_bot.py       # Telegram komut botu (long-polling)
│   └── trader.py             # Hisse işlemleri (placeholder)
├── utils/
│   ├── helpers.py            # Screenshot, Telegram mesaj/fotoğraf, retry
│   └── logger.py             # Dosya + konsol loglama
├── deploy/
│   ├── deploy.sh             # Sunucu güncelleme scripti
│   ├── setup.sh              # İlk kurulum scripti
│   ├── webhook_listener.py   # GitHub webhook → otomatik deploy
│   └── ihlamur-webhook.service  # systemd servis tanımı
├── main.py                   # Ana giriş noktası
├── requirements.txt
└── .env.example
```

---

## ✅ Tamamlananlar

### 1. Giriş Akışı (`core/auth.py`)

KuveytTürk İnternet Şubesi klasik HTML/jQuery sitedir.  
Giriş 8 adımdan oluşur:

| Adım | İşlem | Teknik Detay |
|------|-------|-------------|
| 0 | Popup kapat + Bireysel sekmesi | `WebDriverWait` |
| 1 | Müşteri No | `contenteditable div` — char-by-char `execCommand('insertText')` + blur |
| 2 | Şifre | M0–M43 sanal klavye butonlarına tıklama |
| 3 | Telefon No | JS `value` set + `input/change` event dispatch |
| 4 | CAPTCHA | Screenshot → Telegram → kullanıcı gönderir → Telegram polling |
| 5 | DEVAM butonu | JS click |
| 6 | Güvenlik resmi (Türk bayrağı) | GİRİŞ butonuna JS click |
| 7 | Mobil onay bekle | URL değişimi veya dashboard keyword kontrolü |

**Güvenlik bypassları:**
- `CustomerNumberDisplay`: `charDiff > 1` koruması — her karakter tek tek yazılır
- `Password`: readonly kaldırma + sanal klavye tıklama
- DigitMap: sunucu tarafında halloluyor, bypass gerekmez
- CAPTCHA: Telegram üzerinden manuel

### 2. Cookie / Oturum Yönetimi (`core/session.py`)

- Login sonrası tüm cookie'ler `session/cookies.json`'a kaydedilir
- Bot yeniden başlatılırken önce cookie ile restore denenir — başarılıysa **CAPTCHA + mobil onay atlanır**
- Cookie yaşı `SESSION_MAX_AGE` (30 dk) geçince geçersiz sayılır, yeniden giriş yapılır
- Arka plan thread'i (`start_keepalive`) her `SESSION_CHECK_INTERVAL` (60s) saniyede oturum kontrol eder
- Oturum sona erince Telegram'a bildirim gönderilir

### 3. Telegram Komut Botu (`core/telegram_bot.py`)

Long-polling ile komut dinler. `threading.Lock` ile aynı anda tek ağır işlem çalışır.

| Komut | İşlev |
|-------|-------|
| `/login` | Cookie varsa restore, yoksa tam giriş |
| `/relogin` | Cookie sil + sıfırdan giriş |
| `/logout` | Oturumu kapat, cookie sil |
| `/status` | Oturum durumu, cookie yaşı, URL |
| `/screenshot` | Anlık ekran görüntüsü |
| `/explore` | İnteraktif uzaktan kumanda modu |
| `/cancel` | Botu durdur (SIGINT → `finally` bloğu) |

**Loop / çakışma korumaları:**
- `/` ile başlayan mesajlar CAPTCHA polling'ine gitmez
- Explore modu aktifken serbest mesajlar da CAPTCHA'ya gitmez
- `/cancel`: sadece SIGINT gönderir, temizliği `main.py`'nin `finally` bloğu yapar (çift logout olmaz)

### 4. /explore — İnteraktif Uzaktan Kumanda

`/explore` yazınca screenshot + tıklanabilir element listesi gelir. Ardından:

```
tıkla #btnSubmit          → ID ile tıkla
tıkla "Hesaplarım"        → Link text ile tıkla
tıkla //a[@href='/...']   → XPath ile tıkla
yaz #GsmNumber 905xxx     → Elemente text yaz
git isube.kuveytturk...   → URL'ye git
scroll aşağı              → Sayfa scroll
bekle 5                   → 5 saniye bekle
js document.title         → JavaScript çalıştır
scan                      → Sayfayı yeniden tara
bitti                     → Explore modundan çık
```

Her işlemden sonra otomatik screenshot gelir.

### 5. Altyapı

- **Sunucu:** DigitalOcean ubuntu-s-2vcpu-4gb-fra1
- **Browser:** Headless Chrome 146 + ChromeDriver
- **GitHub Webhook:** Push → otomatik deploy (`deploy/webhook_listener.py`)
- **systemd:** `ihlamur-webhook.service` ile webhook listener servis olarak çalışır

---

## ⬜ Yapılacaklar

### Öncelik 1 — Dashboard Keşfi
- `/explore` ile dashboard sayfasını tara
- Hisse senedi / portföy sayfasına giden linkleri bul
- Menü yapısını belgele

### Öncelik 2 — Trader (`core/trader.py`)
- `get_portfolio()` — portföy çekme
- `place_order()` — alım/satım emri
- TradePlus iframe varsa selenium frame switch
- İşlem onay akışı

### Öncelik 3 — Telegram'dan İşlem
- `/portföy` komutu
- `/al THYAO 10 320.50` komutu
- `/sat THYAO 10 325.00` komutu
- İşlem öncesi onay mesajı (evet/hayır)

### Öncelik 4 — Strateji Motoru
- Piyasa verisi kaynağı (API veya scraping)
- Kural tabanlı alım/satım sinyalleri
- Risk yönetimi (max tutar, günlük limit)

---

## 🚀 Kurulum (Sunucu)

```bash
# Repoyu klonla
git clone https://github.com/emirceran23/ihlamur.git ~/ihlamur
cd ~/ihlamur

# Virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# .env dosyasını oluştur
cp .env.example .env
nano .env   # bilgileri gir

# Chrome kur
apt-get update && apt-get install -y wget gnupg
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" \
  > /etc/apt/sources.list.d/google-chrome.list
apt-get update && apt-get install -y google-chrome-stable
```

## ⚙️ Çalıştırma

```bash
# Serve modu (önerilen — Telegram botu aktif)
python main.py

# Tek seferlik giriş testi
python main.py --action login-test

# Sayfa keşif modu (CLI)
python main.py --action explore
```

## 🔑 .env Değişkenleri

```env
KUVEYTTURK_TC=1234567890        # Müşteri No / TC Kimlik No
KUVEYTTURK_PASSWORD=123456      # 6 haneli şifre
KUVEYTTURK_PHONE=905xxxxxxxxx   # Kayıtlı telefon (90 ile başlar)

TELEGRAM_BOT_TOKEN=xxxx:yyyy
TELEGRAM_CHAT_ID=123456789

HEADLESS=true
LOG_LEVEL=INFO
```

---

## ⚠️ Uyarı

Bu bot kişisel kullanım amaçlıdır. Otomatik işlem riskleri tamamen kullanıcıya aittir.
