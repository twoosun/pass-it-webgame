"""Local storage or private Supabase objects. Keys never come from request URLs."""

from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote, urlparse
import mimetypes
import os
import tempfile
import httpx
from fastapi import HTTPException
from .database import DATA, IS_VERCEL

LIMIT = 30 * 1024 * 1024


def remote_enabled():
    configured = bool(
        os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    )
    if IS_VERCEL and not configured:
        raise HTTPException(503, "Supabase 저장소 연결 설정이 필요합니다.")
    return configured


def settings():
    origin = os.environ["SUPABASE_URL"].rstrip("/")
    if urlparse(origin).scheme != "https":
        raise RuntimeError("SUPABASE_URL must be HTTPS")
    token = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return (
        origin + "/storage/v1",
        os.getenv("SUPABASE_BUCKET", "omr-private"),
        {
            "apikey": token,
            "Authorization": "Bearer " + token,
        },
    )


def request(method, endpoint, **kwargs):
    base, _, headers = settings()
    try:
        r = httpx.request(
            method,
            base + endpoint,
            headers={**headers, **kwargs.pop("headers", {})},
            timeout=90,
            **kwargs,
        )
        r.raise_for_status()
        return r
    except httpx.HTTPError as exc:
        # Do not expose provider URLs, signed tokens, or credentials in responses.
        raise HTTPException(
            502, "파일 저장소 요청에 실패했습니다. 잠시 후 다시 시도하세요."
        ) from exc


def object_path(key):
    _, bucket, _ = settings()
    if key.startswith("/") or ".." in key.split("/"):
        raise ValueError("Invalid object key")
    return quote(bucket, safe="") + "/" + quote(key, safe="/")


@lru_cache(maxsize=4)
def require_private_bucket(base, bucket):
    info = request("GET", "/bucket/" + quote(bucket, safe="")).json()
    if info.get("public") is not False:
        raise HTTPException(503, "OMR 저장소는 비공개(Private) 버킷이어야 합니다.")


def signed_url(key, upload=False):
    base, bucket, _ = settings()
    require_private_bucket(base, bucket)
    endpoint = "/object/upload/sign/" if upload else "/object/sign/"
    result = request(
        "POST", endpoint + object_path(key), json={} if upload else {"expiresIn": 300}
    ).json()
    relative = result["url" if upload else "signedURL"]
    base, _, _ = settings()
    # Supabase returns a path relative to /storage/v1.
    return base + relative


def persist(path):
    key = path.relative_to(DATA).as_posix()
    if remote_enabled():
        base, bucket, _ = settings()
        require_private_bucket(base, bucket)
        request(
            "POST",
            "/object/" + object_path(key),
            content=path.read_bytes(),
            headers={
                "Content-Type": mimetypes.guess_type(path.name)[0]
                or "application/octet-stream",
                "x-upsert": "false",
            },
        )
        return "supabase:" + key
    return key


def local_path(key):
    path = (DATA / key).resolve()
    if not path.is_relative_to(DATA.resolve()):
        raise HTTPException(404, "파일을 찾을 수 없습니다")
    return path


@contextmanager
def materialize(key):
    if not key.startswith("supabase:"):
        path = local_path(key)
        if not path.is_file():
            raise HTTPException(404, "파일을 찾을 수 없습니다")
        yield path
        return
    remote_key = key.removeprefix("supabase:")
    base, _, headers = settings()
    with tempfile.TemporaryDirectory(prefix="download-", dir=DATA) as directory:
        path = Path(directory) / ("original" + Path(remote_key).suffix)
        try:
            with httpx.stream(
                "GET",
                base + "/object/authenticated/" + object_path(remote_key),
                headers=headers,
                timeout=90,
            ) as r:
                r.raise_for_status()
                size = 0
                with path.open("wb") as output:
                    for chunk in r.iter_bytes(1024 * 1024):
                        size += len(chunk)
                        if size > LIMIT:
                            raise HTTPException(413, "최대 30MB입니다")
                        output.write(chunk)
                if not size:
                    raise HTTPException(422, "빈 파일입니다")
        except httpx.HTTPError as exc:
            raise HTTPException(502, "업로드 파일을 불러올 수 없습니다.") from exc
        yield path


def delete(key):
    if key.startswith("supabase:"):
        _, bucket, _ = settings()
        request(
            "DELETE",
            "/object/" + quote(bucket, safe=""),
            json={"prefixes": [key.removeprefix("supabase:")]},
        )
    else:
        local_path(key).unlink(missing_ok=True)
