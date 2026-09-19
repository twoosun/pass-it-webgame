"""Generate exact frontend proxy configuration only after a real backend exists."""

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse
import httpx

ROOT = Path(__file__).resolve().parents[1]


def prepare(backend_url):
    origin = backend_url.rstrip("/")
    url = urlparse(origin)
    if (
        url.scheme != "https"
        or not url.netloc
        or url.path not in ("", "/")
        or url.username
        or url.query
        or url.fragment
    ):
        raise ValueError("실제 Python 서버의 HTTPS origin을 입력하세요.")
    response = httpx.get(origin + "/api/health", timeout=30)
    response.raise_for_status()
    if response.json().get("service") != "omr-study":
        raise ValueError("OMR 서버 상태 확인에 실패했습니다.")
    config = {
        "$schema": "https://openapi.vercel.sh/vercel.json",
        "framework": "vite",
        "buildCommand": "npm run build",
        "outputDirectory": "dist",
        "rewrites": [{"source": "/api/:path*", "destination": origin + "/api/:path*"}],
        "headers": [
            {
                "source": "/api/:path*",
                "headers": [{"key": "Cache-Control", "value": "no-store"}],
            }
        ],
    }
    path = ROOT / "frontend/vercel.json"
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print("Wrote", path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("backend_url")
    args = parser.parse_args()
    prepare(args.backend_url)
