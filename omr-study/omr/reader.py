import cv2
import numpy as np
from .scoring import classify_scores


def ink_plane(image):
    """Max channel removes colored print/red annotations, preserving neutral dark ink."""
    plane = image.max(axis=2).copy()
    # Real photographed forms have dark burgundy print, not bright PDF magenta.
    # Remove chromatic ink and its JPEG fringe before illumination normalization.
    spread = plane.astype(np.float32) - image.min(axis=2).astype(np.float32)
    colored = (spread > np.maximum(18, 0.22 * plane)).astype(np.uint8)
    colored = cv2.dilate(colored, np.ones((3, 3), np.uint8))
    plane[colored > 0] = 255
    background = cv2.GaussianBlur(plane, (0, 0), 31)
    return np.clip(
        plane.astype(np.float32) * 255 / np.maximum(background, 80), 0, 255
    ).astype("uint8")


def make_difference(template, aligned):
    template_gray = ink_plane(template)
    aligned_gray = ink_plane(aligned)
    # A small minimum filter tolerates subpixel print edges without inventing marks.
    reference = cv2.erode(template_gray, np.ones((3, 3), np.uint8))
    difference = np.maximum(
        reference.astype(np.int16) - aligned_gray.astype(np.int16), 0
    ).astype("uint8")
    threshold = ((difference > 45) & (aligned_gray < 195)).astype("uint8") * 255
    return aligned_gray, difference, threshold


def extract_bubble_score(gray, difference, point, roi_size, virtual=False):
    h, w = gray.shape
    cx, cy = point[0] * w, point[1] * h
    rx, ry = max(3, roi_size[0] * w / 2), max(4, roi_size[1] * h / 2)
    offsets = [(0, 0)]
    if virtual:
        offsets += [
            (dx * rx, dy * ry) for dx in (-0.65, 0, 0.65) for dy in (-0.75, 0, 0.75)
        ]
    best = 0.0
    for dx, dy in offsets:
        x0, x1 = max(0, int(cx + dx - rx)), min(w, int(cx + dx + rx + 1))
        y0, y1 = max(0, int(cy + dy - ry)), min(h, int(cy + dy + ry + 1))
        p = gray[y0:y1, x0:x1]
        d = difference[y0:y1, x0:x1]
        if not p.size:
            continue
        yy, xx = np.ogrid[: p.shape[0], : p.shape[1]]
        mask = ((xx - (p.shape[1] - 1) / 2) / rx) ** 2 + (
            (yy - (p.shape[0] - 1) / 2) / ry
        ) ** 2 <= 1
        center = ((xx - (p.shape[1] - 1) / 2) / rx) ** 2 + (
            (yy - (p.shape[0] - 1) / 2) / ry
        ) ** 2 <= 0.35
        binary = ((d > 45) & (p < 195) & mask).astype("uint8")
        n, _, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
        component = max(stats[1:, cv2.CC_STAT_AREA], default=0) / max(1, mask.sum())
        strength = float(np.mean(np.clip(d[mask] / 150, 0, 1)))
        score = (
            0.35 * float(binary[mask].mean())
            + 0.25 * float(binary[center].mean())
            + 0.25 * component
            + 0.15 * strength
        )
        best = max(best, score)
    return float(best)


def read_multiple_choice(scores, quality, baseline):
    return classify_scores(scores, quality, baseline)


def read_numeric_answer(columns, quality, baseline):
    digits = []
    for column in columns:
        # Repeated residual print affects most rows in a numeric column equally.
        # Subtract only its robust floor; never promote an isolated weak mark.
        floor = min(0.18, float(np.median(list(column.values()))))
        adjusted = {digit: max(0.0, value - floor) for digit, value in column.items()}
        result = classify_scores(
            adjusted, quality, (max(0, baseline[0] - floor), baseline[1])
        )
        result["raw_scores"] = {k: round(float(v), 4) for k, v in column.items()}
        result["background_score"] = round(floor, 4)
        digits.append(result)
    values = [d["answer"] for d in digits]
    if all(v == "BLANK" for v in values):
        answer, status = "BLANK", "BLANK"
    elif "MULTI" in values:
        answer, status = "MULTI", "MULTI"
    elif "?" in values:
        answer, status = "?", "UNKNOWN"
    else:
        # Leading blanks are legal; internal/trailing blanks are never silently zero-filled.
        start = next(i for i, v in enumerate(values) if v != "BLANK")
        tail = values[start:]
        if "BLANK" in tail:
            answer, status = "?", "UNKNOWN"
        else:
            answer, status = int("".join(map(str, tail))), "OK"
    return {
        "answer": answer,
        "status": status,
        "confidence": min(min(d["confidence"] for d in digits), 0.49)
        if status in ("UNKNOWN", "MULTI")
        else min(d["confidence"] for d in digits),
        "digits": digits,
    }
