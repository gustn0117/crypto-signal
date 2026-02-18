"""GitHub Webhook → 자동 배포 서비스 (v3 - 컨테이너 충돌 해결)"""
import http.server
import subprocess
import hashlib
import hmac
import json
import threading
import time

SECRET = "coin-deploy-secret-2026"
PROJECT_NAME = "crypto-signal"

_deploy_lock = threading.Lock()
_last_deploy_status = {"running": False, "last_result": None, "last_time": None}


def run_deploy():
    """실제 배포 실행 (별도 스레드)"""
    if not _deploy_lock.acquire(blocking=False):
        print("[deploy] 이미 배포 진행 중 - 스킵", flush=True)
        return

    _last_deploy_status["running"] = True
    try:
        print("[deploy] === 배포 시작 ===", flush=True)

        # 1) git pull
        print("[deploy] step 1/4: git pull", flush=True)
        r = subprocess.run(
            ["git", "pull", "--ff-only"], cwd="/repo",
            capture_output=True, text=True, timeout=60,
        )
        print(f"[deploy] git pull: {r.stdout.strip()}", flush=True)
        if r.returncode != 0:
            print(f"[deploy] git pull 실패: {r.stderr}", flush=True)
            _last_deploy_status["last_result"] = "FAILED (git pull)"
            return

        # 2) 기존 컨테이너 강제 제거 (이름 충돌 방지)
        print("[deploy] step 2/4: 기존 컨테이너 제거", flush=True)
        for name in ["coin-backend", "coin-frontend"]:
            subprocess.run(
                ["docker", "rm", "-f", name],
                capture_output=True, text=True, timeout=30,
            )

        # 3) docker compose down (네트워크 등 정리)
        print("[deploy] step 3/4: docker compose down", flush=True)
        subprocess.run(
            ["docker", "compose", "-p", PROJECT_NAME, "down", "--timeout", "10"],
            cwd="/repo", capture_output=True, text=True, timeout=120,
        )

        # 4) docker compose up --build
        print("[deploy] step 4/4: docker compose up -d --build", flush=True)
        r = subprocess.run(
            ["docker", "compose", "-p", PROJECT_NAME, "up", "-d", "--build"],
            cwd="/repo", capture_output=True, text=True, timeout=600,
        )
        if r.stdout:
            print(f"[deploy] stdout: {r.stdout}", flush=True)
        if r.stderr:
            print(f"[deploy] stderr: {r.stderr}", flush=True)

        if r.returncode == 0:
            print("[deploy] === 배포 성공 ===", flush=True)
            _last_deploy_status["last_result"] = "SUCCESS"
        else:
            print(f"[deploy] === 배포 실패 (exit={r.returncode}) ===", flush=True)
            _last_deploy_status["last_result"] = f"FAILED (exit={r.returncode})"

    except subprocess.TimeoutExpired:
        print("[deploy] === 배포 타임아웃 ===", flush=True)
        _last_deploy_status["last_result"] = "TIMEOUT"
    except Exception as e:
        print(f"[deploy] === 배포 에러: {e} ===", flush=True)
        _last_deploy_status["last_result"] = f"ERROR: {e}"
    finally:
        _last_deploy_status["running"] = False
        _last_deploy_status["last_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _deploy_lock.release()


class DeployHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(_last_deploy_status).encode())
            return
        if self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
            return
        self.send_response(404)
        self.end_headers()

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

        if _last_deploy_status["running"]:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Deploy already running")
            return

        threading.Thread(target=run_deploy, daemon=True).start()

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Deploy triggered")

    def log_message(self, fmt, *args):
        print(f"[webhook] {args[0]}", flush=True)


if __name__ == "__main__":
    print(f"Webhook server running on :9000 (project={PROJECT_NAME})", flush=True)
    server = http.server.HTTPServer(("0.0.0.0", 9000), DeployHandler)
    server.serve_forever()
