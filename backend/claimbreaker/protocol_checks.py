"""Conservative paper/protocol cross-checks with inspectable correspondence."""

import re
from .checks import finding, stable, at_line


def protocol_checks(artifacts, decisions=None):
    findings, checks = [], []
    correspondence = next(
        (
            d["answer"]
            for d in reversed(decisions or [])
            if d["question_id"] == "repository-version"
        ),
        None,
    )
    noncorresponding = correspondence in {"different", "unknown"}
    codes = [a for a in artifacts if a["parsed"].get("code", {}).get("estimator")]
    if len(codes) != 1:
        return findings, checks
    code = codes[0]
    profile = code["parsed"]["code"]
    split_call = next(
        (c for c in profile.get("calls", []) if c["name"] == "train_test_split"), None
    )
    split_anchor = at_line(code, split_call["line"]) if split_call else None
    code_evidence = [split_anchor] if split_anchor else code["parsed"].get("anchors", [])[:1]
    for paper in [a for a in artifacts if a["kind"] in {"paper", "documentation"}]:
        for source in paper["parsed"].get("anchors", []):
            text = source["text"]
            candidates = []
            seed = re.search(r"(?:random\s+seed\s*(?:of|is|was|=|:)?\s*)(\d+)", text, re.I)
            if seed and profile.get("seed") is not None:
                candidates.append(("Random seed", int(seed.group(1)), profile["seed"], 0))
            split = re.search(
                r"(\d+(?:\.\d+)?)%\s+(?:held[- ]out\s+)?test\s+(?:partition|split|set)", text, re.I
            )
            if split and profile.get("split") == "random":
                raw = split.group(1)
                decimals = len(raw.split(".")[1]) if "." in raw else 0
                candidates.append(
                    (
                        "Test fraction",
                        float(raw) / 100,
                        profile.get("test_size", 0.25),
                        0.5 * 10**-decimals / 100,
                    )
                )
            for label, reported, actual, tolerance in candidates:
                same = abs(reported - actual) <= tolerance + 1e-12
                checks.append(
                    {
                        "id": stable("check", source["id"] + code["id"] + label),
                        "name": "Paper ↔ code " + label.lower(),
                        "status": "passed"
                        if same
                        else "inconclusive"
                        if noncorresponding
                        else "flagged",
                        "detail": f"Paper {reported}; source {actual}. Source corresponds to {code['path']}.",
                    }
                )
                if not same:
                    findings.append(
                        finding(
                            label + " differs between paper and source",
                            "protocol_configuration",
                            "inconclusive" if noncorresponding else "supported_concern",
                            "informational" if noncorresponding else "medium",
                            "The paper's explicit evaluation setting differs from the single discovered model entry point.",
                            [source, *code_evidence],
                            {"setting": label, "paper_setting": reported, "code_setting": actual},
                            ["The source may represent another experiment or release"],
                            [
                                "Single-entry-point discovery does not by itself prove publication correspondence"
                            ],
                            "Confirm the source version and experiment, then inspect this protocol setting.",
                        )
                    )
            trials = re.search(
                r"(?:over|across|ran)\s+(\d+)\s+(?:independent\s+)?(?:trials|seeds|runs)\b",
                text,
                re.I,
            )
            if trials:
                declared = int(trials.group(1))
                for result in [a for a in artifacts if a["kind"] == "results"]:
                    structured = result["parsed"].get("structured", {})
                    if not isinstance(structured, dict):
                        continue
                    runs = structured.get(
                        "runs", structured.get("trials", structured.get("trial_manifest"))
                    )
                    if not isinstance(runs, list):
                        continue
                    checks.append(
                        {
                            "id": stable("check", source["id"] + result["id"] + "trials"),
                            "name": "Released trial evidence",
                            "status": "passed" if len(runs) == declared else "inconclusive",
                            "detail": f"Paper mentions {declared} trials; supplied artifact contains {len(runs)} records. Missing records do not disprove the paper.",
                        }
                    )
    return findings, checks
