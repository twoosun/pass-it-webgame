from pathlib import Path
import csv, json
import cv2
import numpy as np
import pymupdf
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]


def read_image(path):
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        if im.width * im.height > 50_000_000:
            raise ValueError("Image exceeds 50 megapixels")
        return cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)


def write_image(path, image):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imencode(path.suffix, image)[1].tofile(str(path))


def load_pages(path):
    if Path(path).suffix.lower() == ".pdf":
        with pymupdf.open(path) as doc:
            if len(doc) > 30:
                raise ValueError("At most 30 pages per PDF")
            for page in doc:
                scale = min(3, 2600 / max(page.rect.width, page.rect.height))
                pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
                yield cv2.cvtColor(
                    np.frombuffer(pix.samples, np.uint8).reshape(
                        pix.height, pix.width, 3
                    ),
                    cv2.COLOR_RGB2BGR,
                )
    else:
        yield read_image(path)


def read_page(path, page_number):
    """Read one PDF page without rendering earlier pages on each request."""
    if Path(path).suffix.lower() != ".pdf":
        if page_number != 1:
            raise ValueError("이미지에는 1페이지만 있습니다")
        return read_image(path)
    with pymupdf.open(path) as doc:
        if doc.needs_pass or not 1 <= page_number <= len(doc) <= 30:
            raise ValueError("PDF 페이지 범위는 1~30입니다")
        page = doc[page_number - 1]
        scale = min(3, 2600 / max(page.rect.width, page.rect.height))
        pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        return cv2.cvtColor(
            np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3),
            cv2.COLOR_RGB2BGR,
        )


def export_results(results, path):
    path = Path(path)
    if path.suffix.lower() == ".csv":
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["date", "subject", "question", "answer", "confidence"])
            for page in results:
                for q, r in page.get("answers", {}).items():
                    writer.writerow(
                        [page["date"], page["subject"], q, r["answer"], r["confidence"]]
                    )
    else:
        path.write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
