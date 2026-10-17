"""Disposable parser process. Uploaded source is never imported or executed."""

import base64
import json
import os
import sys
from types import SimpleNamespace


def main():
    if sys.platform != "win32":
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (25, 30))
        resource.setrlimit(resource.RLIMIT_AS, (3 * 1024**3, 3 * 1024**3))
        resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024**2, 16 * 1024**2))
    from .parsing import parse

    payload = json.load(sys.stdin)
    artifact = SimpleNamespace(**payload["artifact"])
    if payload.get("operation") == "render":
        from .pdf_tools import render_page
        parsed = render_page(base64.b64decode(payload["data"]), payload["page"], payload.get("quote", ""))
    else:
        parsed = parse(artifact, base64.b64decode(payload["data"]))
    body = json.dumps(parsed, allow_nan=False, default=str)
    if len(body) > 8 * 1024**2:
        raise ValueError("Parsed evidence exceeds the 8 MB per-artifact budget")
    print(body)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(
            json.dumps(
                {
                    "text": "",
                    "anchors": [],
                    "warnings": [f"Parser could not inspect this file: {type(exc).__name__}"],
                    "unavailable": True,
                }
            )
        )
