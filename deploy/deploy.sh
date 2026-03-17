#!/bin/bash
# ─────────────────────────────────────────────────────────
# İhlamur Auto Deploy Script
# GitHub push → Droplet otomatik güncelleme
# ─────────────────────────────────────────────────────────

set -e

PROJECT_DIR="/root/ihlamur"
LOG_FILE="/root/ihlamur/logs/deploy.log"
VENV_DIR="$PROJECT_DIR/venv"

mkdir -p "$(dirname $LOG_FILE)"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "🚀 Deploy başlatıldı..."

cd "$PROJECT_DIR"

# Git pull
log "📥 Git pull yapılıyor..."
git fetch origin
git reset --hard origin/master
log "✅ Kod güncellendi."

# Bağımlılıkları güncelle
log "📦 Bağımlılıklar kontrol ediliyor..."
source "$VENV_DIR/bin/activate"
pip install -r requirements.txt --quiet
log "✅ Bağımlılıklar güncellendi."

# .env dosyasını koru (git'ten gelmez)
if [ ! -f "$PROJECT_DIR/.env" ]; then
    log "⚠️  .env dosyası bulunamadı! cp .env.example .env yapıp doldurun."
fi

log "🌳 Deploy tamamlandı!"
