#!/usr/bin/env python3
"""
GitHub Webhook Listener
Push geldiğinde deploy.sh çalıştırır.
Droplet üzerinde sürekli çalışır (systemd ile).
"""

import hashlib
import hmac
import json
import os
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler

# Webhook secret - GitHub'da ayarladığın secret ile aynı olmalı
WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "ihlamur-deploy-secret")
DEPLOY_SCRIPT = "/root/ihlamur/deploy/deploy.sh"
PORT = 9000


class WebhookHandler(BaseHTTPRequestHandler):

    def do_POST(self):
        if self.path != "/webhook":
            self.send_response(404)
            self.end_headers()
            return

        content_length = int(self.headers.get("Content-Length", 0))
        payload = self.rfile.read(content_length)

        # ── İmza doğrulama ────────────────────────────────
        signature = self.headers.get("X-Hub-Signature-256", "")
        if not self._verify_signature(payload, signature):
            print("❌ İmza doğrulaması başarısız!")
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"Invalid signature")
            return

        # ── Event kontrolü ────────────────────────────────
        event = self.headers.get("X-GitHub-Event", "")
        if event != "push":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Ignored event")
            return

        # ── Branch kontrolü ───────────────────────────────
        try:
            data = json.loads(payload)
            ref = data.get("ref", "")
            if ref != "refs/heads/master":
                print(f"ℹ️  {ref} branch'i ignore edildi.")
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"Not master branch")
                return
        except json.JSONDecodeError:
            pass

        # ── Deploy çalıştır ───────────────────────────────
        print("🚀 Push algılandı, deploy başlatılıyor...")
        try:
            result = subprocess.run(
                ["bash", DEPLOY_SCRIPT],
                capture_output=True,
                text=True,
                timeout=120,
            )
            print(f"Deploy stdout: {result.stdout}")
            if result.returncode != 0:
                print(f"Deploy stderr: {result.stderr}")

            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Deploy triggered")
        except Exception as e:
            print(f"❌ Deploy hatası: {e}")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode())

    def _verify_signature(self, payload: bytes, signature: str) -> bool:
        # Secret ayarlanmamışsa veya imza gelmemişse geç
        if not WEBHOOK_SECRET or not signature:
            return True
        expected = "sha256=" + hmac.new(
            WEBHOOK_SECRET.encode(), payload, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def log_message(self, format, *args):
        print(f"[Webhook] {args[0]}")


def main():
    server = HTTPServer(("0.0.0.0", PORT), WebhookHandler)
    print(f"🌳 İhlamur Webhook Listener başlatıldı - port {PORT}")
    print(f"   Endpoint: http://0.0.0.0:{PORT}/webhook")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Webhook listener durduruldu.")
        server.server_close()


if __name__ == "__main__":
    main()
