import asyncio, io, json
from pathlib import Path
from types import SimpleNamespace
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.utils import ImageReader
from claimbreaker.pdf_tools import render_page
from claimbreaker.parser_process import parse_bounded
from claimbreaker.providers import ModelProvider
from claimbreaker.ocr import recover_pages, verification_questions


async def main():
    original = io.BytesIO()
    c = Canvas(original)
    c.setFont("Helvetica", 18)
    c.drawString(50, 750, "SYNTHETIC OCR ACCEPTANCE FIXTURE")
    c.setFont("Helvetica", 13)
    c.drawString(50, 700, "Test accuracy: 91.2% across 250 participants.")
    c.drawString(50, 675, "Training: 180 samples. Test: 70 samples.")
    c.save()
    page = render_page(original.getvalue(), 1)
    import base64

    raster = base64.b64decode(page["image"].split(",")[1])
    scan = io.BytesIO()
    c = Canvas(scan)
    c.drawImage(ImageReader(io.BytesIO(raster)), 0, 0, width=595, height=842)
    c.save()
    a = SimpleNamespace(id="scanned-acceptance", path="scanned.pdf", kind="paper")
    a.parsed = await parse_bounded(a, scan.getvalue())
    assert a.parsed["page_details"][0]["low_text"]
    provider = ModelProvider("openai")
    parsed, used = await recover_pages(a, scan.getvalue(), provider, 1)
    assert (
        used == 1
        and "91.2%" in parsed["text"]
        and any(x["kind"] == "ocr_passage" for x in parsed["anchors"])
    )
    questions = verification_questions([dict(id=a.id, path=a.path, parsed=parsed)], [])
    assert len(questions) == 1 and questions[0]["answer"] is None
    root = Path("tmp/ocr-acceptance")
    root.mkdir(exist_ok=True)
    (root / "scanned.pdf").write_bytes(scan.getvalue())
    (root / "result.json").write_text(
        json.dumps({"provider": provider.used, "parsed": parsed, "questions": questions}, indent=2)
    )
    print(
        json.dumps(
            {
                "provider": provider.used,
                "attempts": used,
                "recovered": True,
                "human_confirmation_required": True,
            }
        )
    )


asyncio.run(main())
