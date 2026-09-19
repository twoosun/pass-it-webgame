"""Real raster templates with deterministic marks and independent layout checks."""

import cv2
import numpy as np
import pytest
from omr import OMREngine
from omr.io import ROOT, write_image
from omr.reader import read_numeric_answer
from omr.student_number import validate_date


@pytest.fixture(scope="module")
def engine():
    return OMREngine()


def marked(engine, subject="math", date="20260930"):
    image = engine.images[subject].copy()
    h, w = image.shape[:2]
    config = engine.config[subject]

    def mark(p, color=12, shift=(0, 0)):
        cv2.ellipse(
            image,
            (round(p[0] * w) + shift[0], round(p[1] * h) + shift[1]),
            (8, 12),
            0,
            0,
            360,
            (color,) * 3,
            -1,
        )

    for i, (col, d) in enumerate(zip(config["student_number"]["columns"], date)):
        mark(col["digits"][d], shift=(4, -4) if i == 6 else (0, 0))
    expected = {}
    for number, spec in config["questions"].items():
        if spec["type"] == "choice":
            answer = int(number) % 5 + 1
            mark(spec["options"][str(answer)])
            expected[number] = answer
        else:
            answer = {
                16: 128,
                17: 24,
                18: 5,
                19: 100,
                20: 909,
                21: 27,
                22: 0,
                29: 163,
                30: 10,
            }[int(number)]
            for col, d in zip(spec["columns"], str(answer).rjust(3)):
                if d != " ":
                    mark(col["digits"][d])
            expected[number] = answer
    # One blank, one double mark, and an erased ghost; these must not be guessed.
    for number in ("2", "3", "4"):
        for p in config["questions"][number]["options"].values():
            x, y = round(p[0] * w), round(p[1] * h)
            image[y - 18 : y + 19, x - 15 : x + 16] = engine.images[subject][
                y - 18 : y + 19, x - 15 : x + 16
            ]
    expected["2"] = "BLANK"
    for answer in ("1", "5"):
        mark(config["questions"]["3"]["options"][answer])
    expected["3"] = "MULTI"
    mark(config["questions"]["4"]["options"]["2"], 220)
    expected["4"] = "BLANK"
    return image, expected


def transform(image, mode):
    h, w = image.shape[:2]
    if mode == "rotate":
        return cv2.warpAffine(
            image,
            cv2.getRotationMatrix2D((w / 2, h / 2), 5, 0.88),
            (w, h),
            borderValue=(235, 235, 235),
        )
    if mode == "portrait":
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    if mode == "perspective":
        src = np.float32([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]])
        dst = np.float32([[150, 110], [w - 200, 0], [w - 20, h - 90], [30, h - 170]])
        return cv2.warpPerspective(
            image,
            cv2.getPerspectiveTransform(src, dst),
            (w, h),
            borderValue=(220, 220, 220),
        )
    if mode == "bright":
        return np.clip(image.astype(float) * 0.85 + 37, 0, 255).astype("uint8")
    if mode == "dark":
        return (image * 0.57).astype("uint8")
    if mode == "shadow":
        gradient = np.linspace(0.45, 1, w)[None, :, None]
        return (image * gradient).astype("uint8")
    if mode == "red":
        image = image.copy()
        cv2.circle(image, (860, 255), 35, (30, 30, 220), 9)
        cv2.line(image, (845, 180), (850, 930), (25, 25, 210), 7)
        return image
    return image


@pytest.mark.parametrize("subject", ["korean", "math", "english"])
def test_all_questions(engine, subject):
    image, expected = marked(engine, subject)
    result = engine.analyze(image)
    assert result["subject"] == subject
    assert result["date"] == "2026-0930"
    assert {q: r["answer"] for q, r in result["answers"].items()} == expected


@pytest.mark.parametrize(
    "mode", ["rotate", "portrait", "perspective", "bright", "dark", "shadow", "red"]
)
def test_capture_conditions(engine, mode):
    image, expected = marked(engine)
    image = transform(image, mode)
    result = engine.analyze(image)
    assert result["date"] == "2026-0930", result["date_details"]
    assert {q: r["answer"] for q, r in result["answers"].items()} == expected


def test_virtual_position_not_printed(engine):
    config = engine.config["math"]
    p = config["student_number"]["columns"][6]["digits"]["3"]
    # Independent observed geometry: seventh column at preview x≈264.5, digit 3 y≈523.
    assert abs(p[0] * 1263 - 264.5) < 2
    assert abs(p[1] * 893 - 523) < 2
    x, y = round(p[0] * 2526), round(p[1] * 1786)
    crop = engine.images["math"][y - 10 : y + 11, x - 6 : x + 7]
    assert (crop.min(axis=2) > 230).mean() > 0.95, (
        "Virtual slot should contain no printed bubble"
    )
    image, _ = marked(engine)
    write_image(ROOT / "output/test-fixtures/virtual-20260930.png", image)
    assert engine.analyze(image)["date"] == "2026-0930"


def test_weak_mark_is_not_forced(engine):
    image = engine.images["math"].copy()
    p = engine.config["math"]["questions"]["1"]["options"]["2"]
    cv2.ellipse(
        image,
        (round(p[0] * image.shape[1]), round(p[1] * image.shape[0])),
        (8, 12),
        0,
        0,
        360,
        (205, 205, 205),
        -1,
    )
    result = engine.analyze(image)
    assert result["answers"]["1"]["answer"] in ("?", "BLANK")


def test_reject_unrelated(engine):
    with pytest.raises(ValueError):
        engine.analyze(np.full((900, 1300, 3), 255, np.uint8))


def test_reject_cropped_answers(engine):
    with pytest.raises(ValueError):
        engine.analyze(engine.images["english"][:1350, :, :])


def test_multipage_pdf_order_independent(engine, tmp_path):
    import pymupdf

    path = tmp_path / "mixed.pdf"
    doc = pymupdf.open()
    for subject in ("english", "korean", "math"):
        image, _ = marked(engine, subject)
        page = doc.new_page(width=842, height=595)
        page.insert_image(page.rect, stream=cv2.imencode(".png", image)[1].tobytes())
    doc.save(path)
    doc.close()
    results = engine.analyze_file(path)
    assert [r["subject"] for r in results] == ["english", "korean", "math"]
    assert all(r["date"] == "2026-0930" for r in results)


def test_blank_and_invalid_dates(engine):
    r = engine.analyze(engine.images["english"])
    assert all(v["answer"] == "BLANK" for v in r["answers"].values())
    assert r["date"] == "????-????"
    assert validate_date("20260231")[0] is None
    assert validate_date("20240229")[0] == "2024-02-29"
    assert validate_date("20260229")[0] is None


def test_numeric_internal_blank():
    scores = lambda d: {str(i): 0.95 if i == d else 0 for i in range(10)}
    assert (
        read_numeric_answer([scores(1), scores(-1), scores(8)], 1, (0, 0))["answer"]
        == "?"
    )
    assert (
        read_numeric_answer([scores(-1), scores(2), scores(4)], 1, (0, 0))["answer"]
        == 24
    )
