"""Calibrate the supplied 2026 raster OMR PDF; never OCR handwritten answers."""

from pathlib import Path
import sys, json, hashlib
import cv2
import numpy as np
import pymupdf

ROOT = Path(__file__).resolve().parents[1]
SUBJECTS = ("korean", "math", "english")
# Layout bands measured on the supplied PDF, in its 1263 x 893 preview.
# These select semantic blocks; every bubble center is measured from the raster.
BLOCKS = {
    "korean": [
        (1, 20, 535, 640, 135, 840),
        (21, 14, 687, 790, 135, 625),
        (35, 11, 955, 1060, 135, 515),
    ],
    "english": [
        (1, 20, 525, 630, 135, 840),
        (21, 20, 762, 868, 135, 840),
        (41, 5, 999, 1105, 135, 300),
    ],
    "math": [
        (1, 10, 454, 558, 117, 462),
        (11, 5, 606, 711, 117, 282),
        (23, 6, 876, 981, 530, 732),
    ],
}
NUMERIC = {
    16: (1000, 1061, 117, 462),
    17: (1087, 1147, 117, 462),
    18: (412, 471, 530, 876),
    19: (499, 558, 530, 876),
    20: (586, 645, 530, 876),
    21: (672, 732, 530, 876),
    22: (759, 818, 530, 876),
    29: (1000, 1061, 530, 876),
    30: (1087, 1147, 530, 876),
}


def clusters(values, tolerance=3):
    groups = []
    for value in sorted(values):
        if not groups or value - np.mean(groups[-1]) > tolerance:
            groups.append([value])
        else:
            groups[-1].append(value)
    return [float(np.median(g)) for g in groups]


def detect_bubbles(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    contours, _ = cv2.findContours(
        (gray < 240).astype("uint8"), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE
    )
    return [
        (x + w / 2, y + h / 2)
        for c in contours
        for x, y, w, h in [cv2.boundingRect(c)]
        if 7 <= w <= 12 and 13 <= h <= 17
    ]


def grid(points, band, nx, ny):
    left, right, top, bottom = band
    p = [(x, y) for x, y in points if left < x < right and top < y < bottom]
    xs = clusters([x for x, y in p])
    ys = clusters([y for x, y in p])
    if len(xs) != nx or len(ys) != ny:
        raise ValueError(
            f"Calibration failed in {band}: expected {nx}x{ny}, found {xs}, {ys}. Inspect PDF / use manual calibration."
        )
    return xs, ys


def calibrate(pdf):
    config = {}
    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)
    with pymupdf.open(pdf) as doc:
        if len(doc) < 3:
            raise ValueError("Three template pages are required")
        for index, subject in enumerate(SUBJECTS):
            pix = doc[index].get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
            image = cv2.cvtColor(
                np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3),
                cv2.COLOR_RGB2BGR,
            )
            points = detect_bubbles(image)
            norm = lambda x, y: [round(x / pix.width, 8), round(y / pix.height, 8)]
            xs, ys = grid(points, (105, 293, 405, 750), 8, 10)
            # The fourth-to-fifth digit gap contains the printed hyphen. Preserve it.
            dy = float(np.median(np.diff(ys)))
            y0 = float(np.median([y - i * dy for i, y in enumerate(ys)]))
            columns = [
                {"digits": {str(d): norm(x, y0 + d * dy) for d in range(10)}}
                for x in xs
            ]
            questions = {}
            for start, count, left, right, top, bottom in BLOCKS[subject]:
                qx, qy = grid(points, (left, right, top, bottom), 5, count)
                for i, y in enumerate(qy):
                    questions[str(start + i)] = {
                        "type": "choice",
                        "options": {str(k + 1): norm(x, y) for k, x in enumerate(qx)},
                    }
            if subject == "math":
                for number, band in NUMERIC.items():
                    qx, qy = grid(points, band, 3, 10)
                    questions[str(number)] = {
                        "type": "numeric",
                        "columns": [
                            {
                                "digits": {
                                    str(d): norm(x, y)
                                    for d, y in enumerate(qy)
                                    if col > 0 or d > 0
                                }
                            }
                            for col, x in enumerate(qx)
                        ],
                    }
            high = doc[index].get_pixmap(matrix=pymupdf.Matrix(3, 3), alpha=False)
            high.save(str(assets / f"template_{subject}.png"))
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            contours, _ = cv2.findContours(
                (gray < 80).astype("uint8"), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            markers = [
                norm(x + w / 2, y + h / 2)
                for c in contours
                for x, y, w, h in [cv2.boundingRect(c)]
                if 5 <= w <= 12 and 9 <= h <= 20 and (y < 30 or x > 1155 or y > 850)
            ]
            config[subject] = {
                "size": [high.width, high.height],
                "template": f"assets/template_{subject}.png",
                "roi_size": [8 / pix.width, 12 / pix.height],
                "student_number": {"columns": columns, "step_y": dy / pix.height},
                "questions": dict(sorted(questions.items(), key=lambda t: int(t[0]))),
                "markers": markers,
                "source_page": index + 1,
                "source_sha256": hashlib.sha256(Path(pdf).read_bytes()).hexdigest(),
            }
            print(
                subject,
                f"{high.width}x{high.height}",
                len(questions),
                "questions",
                len(markers),
                "markers",
                "digit step",
                dy,
            )
    (ROOT / "config").mkdir(exist_ok=True)
    (ROOT / "config/templates.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return config


if __name__ == "__main__":
    calibrate(sys.argv[1])
