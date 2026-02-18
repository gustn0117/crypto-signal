"""GitHub Webhook → 자동 배포 서비스"""
import http.server
import subprocess
import hashlib
import hmac
import json

SECRET = "coin-deploy-secret-2026"


class DeployHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/deploy":
            self.send_response(404)
            self.end_headers()
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        # GitHub signature 검증
        sig = self.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(
            SECRET.encode(), body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"Invalid signature")
            return

        # push 이벤트만 처리
        event = self.headers.get("X-GitHub-Event", "")
        if event != "push":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Ignored: not a push event")
            return

        # 배포 실행 (비동기)
        subprocess.Popen(
            ["sh", "-c", "cd /repo/backend && git pull && docker compose up -d --build"],
        )

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Deploy triggered")

    def log_message(self, fmt, *args):
        print(f"[webhook] {args[0]}")


if __name__ == "__main__":
    server = http.server.HTTPServer(("0.0.0.0", 9000), DeployHandler)
    print("Webhook server running on :9000")
    server.serve_forever()
