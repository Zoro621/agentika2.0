from pathlib import Path
import httpx
from .config import settings


def local_path(key: str) -> Path:
    root = (settings().data_dir / "artifacts").resolve()
    target = (root / key).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Invalid storage path")
    return target


def put(key: str, data: bytes):
    cfg = settings()
    path = local_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if cfg.supabase_url and not cfg.offline:
        headers = {
            "Authorization": f"Bearer {cfg.supabase_service_key}",
            "apikey": cfg.supabase_service_key,
            "x-upsert": "true",
            "Content-Type": "application/octet-stream",
        }
        response = httpx.post(
            f"{cfg.supabase_url.rstrip('/')}/storage/v1/object/{cfg.storage_bucket}/{key}",
            headers=headers,
            content=data,
            timeout=40,
        )
        response.raise_for_status()


def get(key: str) -> bytes:
    path = local_path(key)
    if path.exists():
        return path.read_bytes()
    cfg = settings()
    if cfg.supabase_url and not cfg.offline:
        response = httpx.get(
            f"{cfg.supabase_url.rstrip('/')}/storage/v1/object/authenticated/{cfg.storage_bucket}/{key}",
            headers={
                "Authorization": f"Bearer {cfg.supabase_service_key}",
                "apikey": cfg.supabase_service_key,
            },
            timeout=40,
        )
        response.raise_for_status()
        return response.content
    raise FileNotFoundError(key)


def delete(key: str):
    cfg = settings()
    if cfg.supabase_url and not cfg.offline:
        response = httpx.request(
            "DELETE",
            f"{cfg.supabase_url.rstrip('/')}/storage/v1/object/{cfg.storage_bucket}",
            headers={
                "Authorization": f"Bearer {cfg.supabase_service_key}",
                "apikey": cfg.supabase_service_key,
            },
            json={"prefixes": [key]},
            timeout=20,
        )
        if response.status_code not in (200, 204, 404):
            response.raise_for_status()
    local_path(key).unlink(missing_ok=True)
