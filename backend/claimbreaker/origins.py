"""Exact browser-origin comparison, including deployments behind HTTPS proxies."""

from urllib.parse import urlsplit


def normalize_origin(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or any(char.isspace() for char in value)
    ):
        raise ValueError("Expected an HTTP(S) origin without a path, credentials or query")
    port = parsed.port
    host = parsed.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    default = 443 if parsed.scheme == "https" else 80
    suffix = f":{port}" if port is not None and port != default else ""
    return f"{parsed.scheme}://{host}{suffix}"


def mutation_origin_allowed(origin: str, request_base: str, public_origin: str = "") -> bool:
    try:
        return normalize_origin(origin) == normalize_origin(public_origin or request_base)
    except ValueError:
        return False
