"""Ground model-suggested claims in immutable text and independent numeric parsing."""

from .checks import extract_claims, locate, stable


def merge_claims(inventory, claims, batch, provider):
    index = {a["id"]: a for a in inventory}
    claims = [dict(c) for c in claims]
    for suggestion in batch.claims:
        artifact = index.get(suggestion.artifact_id)
        if not artifact:
            continue
        quote = " ".join(suggestion.quote.split())
        if len(quote) < 10:
            continue
        if quote not in " ".join(artifact["parsed"].get("text", "").split()):
            continue
        context = {
            k: v
            for k, v in {
                "dataset": suggestion.dataset,
                "model": suggestion.model,
                "split": suggestion.split,
            }.items()
            if v and v.lower() in suggestion.quote.lower()
        }
        numeric = (
            extract_claims(
                [{**artifact, "parsed": {**artifact["parsed"], "text": suggestion.quote, "tables": []}}]
            )
            if suggestion.type in {"numerical", "comparison"}
            else []
        )
        if numeric:
            for derived in numeric:
                existing = next(
                    (
                        c
                        for c in claims
                        if c["artifact_id"] == artifact["id"]
                        and c.get("metric") == derived["metric"]
                        and c.get("value") == derived["value"]
                        and c.get("reported") in suggestion.quote
                    ),
                    None,
                )
                if existing:
                    existing["context"] = {**context, **existing.get("context", {})}
                    existing["context_provider"] = provider
                    continue
                derived.update(
                    id=stable(
                        "claim",
                        artifact["id"]
                        + suggestion.quote
                        + derived["metric"]
                        + str(derived["value"]),
                    ),
                    anchor=locate(artifact, derived["quote"]),
                    context={**context, **derived.get("context", {})},
                    origin="deterministic quote validation via " + provider,
                )
                claims.append(derived)
            continue
        if any(
            c["artifact_id"] == artifact["id"] and c["quote"] == suggestion.quote for c in claims
        ):
            continue
        # Broader source statements remain visible, without making model-generated
        # numerical interpretations eligible for deterministic verification.
        claims.append(
            {
                "id": stable("claim", artifact["id"] + suggestion.quote),
                **suggestion.model_dump(),
                "metric": None,
                "value": None,
                "anchor": locate(artifact, suggestion.quote),
                "context": context,
                "origin": provider,
                "tolerance": 0,
                "reported": suggestion.quote[:70],
                "numeric_validation": "contextual statement; no independently parsed quantity",
            }
        )
    return claims
