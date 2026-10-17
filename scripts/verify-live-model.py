"""Explicit opt-in live structured-output check. Never prints credentials."""

import asyncio
import json
from claimbreaker.config import settings
from claimbreaker.providers import ModelProvider
from claimbreaker.schemas import ClaimBatch


async def main():
    provider = ModelProvider("openai")
    result = await provider.generate(
        'Extract this one explicit claim. artifact_id="live-probe". Exact source: "Test accuracy: 91.2% on the held-out cohort."',
        ClaimBatch,
    )
    record = {
        "model": settings().openai_model,
        "provider": provider.used,
        "valid_schema": result is not None,
        "claims": len(result.claims) if result else 0,
        "warnings": provider.warnings,
    }
    print(json.dumps(record))
    if not result or provider.used != "openai":
        raise SystemExit(1)


asyncio.run(main())
