import io
import json
import zipfile

from . import storage
from .report_pdf import pdf_report


def json_report(case):
    return json.dumps(
        {
            "case_id": case.id,
            "title": case.title,
            "revision": case.revision,
            "sources": case.sources,
            "decisions": case.decisions,
            "result": case.result,
        },
        indent=2,
        ensure_ascii=False,
    ).encode()


def evidence_bundle(case, artifacts):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("report.json", json_report(case))
        archive.writestr("report.pdf", pdf_report(case))
        manifest = []
        for a in artifacts:
            archive.writestr("sources/" + a.path, storage.get(a.storage_key))
            manifest.append({"path": a.path, "sha256": a.sha256, "size": a.size})
        archive.writestr(
            "manifest.json",
            json.dumps({"case": case.id, "artifacts": manifest, "sources": case.sources}, indent=2),
        )
        for run in case.result.get("executions", []):
            archive.writestr(
                "runs/" + run["id"] + "/manifest.json", json.dumps(run["manifest"], indent=2)
            )
            archive.writestr(
                "runs/" + run["id"] + "/output.json", json.dumps(run["output"], indent=2)
            )
    return buffer.getvalue()
