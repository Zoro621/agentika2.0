"""Bounded page rasterization and source-word highlight geometry."""

import base64
import io
import re
import pdfplumber
import pypdfium2 as pdfium


def render_page(data, number, quote=""):
    if not 1 <= number <= 100:
        raise ValueError("Page exceeds supported range")
    doc = pdfium.PdfDocument(data)
    if number > len(doc):
        raise ValueError("PDF page does not exist")
    page = doc[number - 1]
    width, height = page.get_size()
    image = page.render(scale=min(2, 1400 / max(width, height))).to_pil()
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    boxes = []
    if quote:
        normalize = lambda text: re.sub(r"[^\w]", "", text.lower())
        wanted = [normalize(word) for word in quote.split() if normalize(word)]
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            words = pdf.pages[number - 1].extract_words(x_tolerance=1.5)
            tokens = [normalize(w["text"]) for w in words]
            for start in range(len(words)):
                length = min(len(wanted), len(words) - start)
                if (
                    length
                    and tokens[start : start + length] == wanted[:length]
                    and length >= min(4, len(wanted))
                ):
                    found = words[start : start + length]
                    for word in found:
                        boxes.append([word["x0"], word["top"], word["x1"], word["bottom"]])
                    break
    page.close()
    doc.close()
    return {
        "image": "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode(),
        "page": number,
        "width": width,
        "height": height,
        "boxes": boxes,
        "highlight": "matched words" if boxes else "no exact word geometry available",
    }
