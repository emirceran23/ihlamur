#!/bin/bash
# ─────────────────────────────────────────────────────────
# İhlamur Droplet İlk Kurulum Scripti
# Droplet'te bir kere çalıştırılır.
# ─────────────────────────────────────────────────────────

set -e

echo "🌳 İhlamur Droplet Kurulumu Başlıyor..."

# ── 1. Sistem bağımlılıkları ──────────────────────────────
echo "📦 Sistem bağımlılıkları kuruluyor..."
apt-get update -y
apt-get install -y python3-venv git wget curl unzip

# ── 1b. Google Chrome kur (snap chromium sürüm sorunu yapar) ──
echo "🌐 Google Chrome kuruluyor..."
wget -q -O /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
apt-get install -y /tmp/chrome.deb || apt-get -f install -y
rm -f /tmp/chrome.deb
echo "✅ Chrome sürümü: $(google-chrome-stable --version)"

# ── 2. Python venv ────────────────────────────────────────
echo "🐍 Python venv oluşturuluyor..."
cd /root/ihlamur
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# ── 3. .env dosyası ───────────────────────────────────────
if [ ! -f .env ]; then
    cp .env.example .env
    echo "⚠️  .env dosyası oluşturuldu. nano .env ile düzenleyin!"
fi

# ── 4. Gerekli klasörler ─────────────────────────────────
mkdir -p logs screenshots

# ── 5. Deploy script'i çalıştırılabilir yap ──────────────
chmod +x deploy/deploy.sh

# ── 6. Webhook servisini kur ─────────────────────────────
echo "🔗 Webhook servisi kuruluyor..."
cp deploy/ihlamur-webhook.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable ihlamur-webhook
systemctl start ihlamur-webhook

# ── 7. Firewall - port 9000 aç ───────────────────────────
echo "🔥 Port 9000 açılıyor..."
ufw allow 9000/tcp 2>/dev/null || true

echo ""
echo "✅ Kurulum tamamlandı!"
echo ""
echo "📋 Yapman gerekenler:"
echo "   1. nano .env  → TC, şifre, Telegram bilgilerini gir"
echo "   2. GitHub repo → Settings → Webhooks → Add webhook"
echo "      Payload URL: http://DROPLET_IP:9000/webhook"
echo "      Content type: application/json"
echo "      Secret: ihlamur-deploy-secret"
echo "      Events: Just the push event"
echo "   3. Test: python main.py --action explore"
echo ""
