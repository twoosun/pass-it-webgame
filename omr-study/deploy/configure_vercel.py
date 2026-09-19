"""Validate local Supabase settings and register server-only Vercel secrets.

Run from omr-study after `vercel link`. Values are never printed or passed in
command-line arguments. This does not upgrade a plan or create a paid resource.
"""

import json
import os
from pathlib import Path
from urllib.parse import urlparse
import httpx

ROOT = Path(__file__).resolve().parents[1]


class ConfigurationError(Exception):
    pass


NAMES = ("DATABASE_URL", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_BUCKET")


def read_settings():
    values = {}
    for line in (
        (ROOT / ".env.vercel.local").read_text(encoding="utf-8-sig").splitlines()
    ):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if separator and key.strip() in NAMES:
            values[key.strip()] = value.strip().strip('"').strip("'")
    missing = [name for name in NAMES if not values.get(name)]
    if missing:
        raise ConfigurationError("Missing settings: " + ", ".join(missing))
    if "[YOUR-PASSWORD]" in values["DATABASE_URL"]:
        raise ConfigurationError(
            "Replace the database password placeholder in DATABASE_URL"
        )
    if not values["DATABASE_URL"].startswith(
        ("postgres://", "postgresql://", "postgresql+psycopg://")
    ):
        raise ConfigurationError("DATABASE_URL must be a PostgreSQL connection URI")
    if urlparse(values["SUPABASE_URL"]).scheme != "https":
        raise ConfigurationError("SUPABASE_URL must use HTTPS")
    return values


def configure():
    values = read_settings()
    link = json.loads((ROOT / ".vercel/project.json").read_text())
    if link.get("projectName") != "omr-study":
        raise ConfigurationError("The linked Vercel project must be omr-study")
    auth_path = (
        Path(os.environ.get("APPDATA", Path.home() / ".local/share"))
        / "com.vercel.cli/Data/auth.json"
    )
    token = json.loads(auth_path.read_text())["token"]
    headers = {"Authorization": "Bearer " + token}
    with httpx.Client(
        base_url="https://api.vercel.com",
        headers=headers,
        params={"teamId": link["orgId"]},
        timeout=30,
    ) as vercel:
        team = vercel.get("/v2/teams/" + link["orgId"])
        team.raise_for_status()
        if team.json().get("billing", {}).get("plan") != "hobby":
            raise ConfigurationError(
                "Expected the selected Hobby team; no settings were changed"
            )

        # Storage and SQL use the same credentials later used by the function.
        os.environ.update(values)
        import sys

        sys.path.insert(0, str(ROOT))
        from backend import storage

        base, bucket, storage_headers = storage.settings()
        response = httpx.get(
            base + "/bucket/" + bucket, headers=storage_headers, timeout=30
        )
        if response.status_code == 404 or (
            response.status_code == 400
            and response.json().get("message") == "Bucket not found"
        ):
            response = httpx.post(
                base + "/bucket",
                headers=storage_headers,
                json={
                    "id": bucket,
                    "name": bucket,
                    "public": False,
                    "file_size_limit": storage.LIMIT,
                },
                timeout=30,
            )
        response.raise_for_status()
        storage.require_private_bucket(base, bucket)
        from backend.database import engine
        from sqlalchemy import text

        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        print("Supabase database and private storage verified.")

        body = [
            {
                "key": name,
                "value": values[name],
                "type": "sensitive",
                "target": ["production"],
            }
            for name in NAMES
        ]
        response = vercel.post(
            "/v10/projects/" + link["projectId"] + "/env",
            params={"upsert": "true", "teamId": link["orgId"]},
            json=body,
        )
        response.raise_for_status()
        print("Registered 4 server-only production variables in omr-study.")


if __name__ == "__main__":
    try:
        configure()
    except ConfigurationError as exc:
        # Our validation errors contain names, never values.
        raise SystemExit(str(exc)) from None
    except Exception as exc:
        # Provider errors can contain connection strings and signed URLs.
        raise SystemExit(
            "Connection setup failed ("
            + type(exc).__name__
            + "). Check the local settings; secret values were not printed."
        ) from None
