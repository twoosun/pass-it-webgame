import json, logging
from pathlib import Path
import numpy as np
from .io import ROOT, read_image, write_image, load_pages
from .alignment import prepare_template, align_to_template
from .subject_detector import detect_page_type
from .reader import (
    make_difference,
    extract_bubble_score,
    read_multiple_choice,
    read_numeric_answer,
)
from .student_number import read_virtual_student_number
from .debug import overlay
from .local_alignment import refine_numeric_grids


class OMREngine:
    def __init__(self, config_path=None):
        self.config = json.loads(
            Path(config_path or ROOT / "config/templates.json").read_text(
                encoding="utf-8"
            )
        )
        self.images = {
            s: read_image(ROOT / c["template"]) for s, c in self.config.items()
        }
        self.prepared = {s: prepare_template(im) for s, im in self.images.items()}

    def analyze(self, image, debug_dir=None):
        candidate = detect_page_type(image, self.prepared)
        subject = candidate["subject"]
        config = self.config[subject]
        warped, aligned, quality, H = align_to_template(
            image, candidate, self.images[subject], config
        )
        aligned, local_quality = refine_numeric_grids(
            self.images[subject], aligned, config
        )
        quality["numeric_grids"] = local_quality
        gray, difference, threshold = make_difference(self.images[subject], aligned)
        score = lambda points, virtual=False: {
            d: extract_bubble_score(gray, difference, p, config["roi_size"], virtual)
            for d, p in points.items()
        }
        question_scores = {
            q: score(spec["options"])
            if spec["type"] == "choice"
            else [score(c["digits"]) for c in spec["columns"]]
            for q, spec in config["questions"].items()
        }
        samples = [
            v
            for s in question_scores.values()
            for group in ([s] if isinstance(s, dict) else s)
            for v in group.values()
        ]
        low = np.sort(samples)[: max(1, int(len(samples) * 0.6))]
        baseline = (float(np.mean(low)), float(np.std(low)))
        answers = {
            q: read_multiple_choice(s, quality["quality"], baseline)
            if isinstance(s, dict)
            else read_numeric_answer(s, quality["quality"], baseline)
            for q, s in question_scores.items()
        }
        date = read_virtual_student_number(
            [score(c["digits"], True) for c in config["student_number"]["columns"]],
            quality["quality"],
            baseline,
        )
        result = {
            "subject": subject,
            "date": date["display"],
            "date_details": date,
            "alignment": quality,
            "answers": answers,
            "warnings": [date["warning"]] if date["warning"] else [],
        }
        result["review_questions"] = [
            q
            for q, r in answers.items()
            if r["status"] in ("UNKNOWN", "MULTI") or r["confidence"] < 0.7
        ]
        for q, r in answers.items():
            logging.debug("%s Q%s %s", subject, q, r)
        if debug_dir:
            directory = Path(debug_dir)
            directory.mkdir(parents=True, exist_ok=True)
            for name, im in {
                "original": image,
                "warped": warped,
                "aligned": aligned,
                "threshold": threshold,
                "difference": difference,
                "roi_overlay": overlay(aligned, config),
                "result_overlay": overlay(aligned, config, result),
            }.items():
                write_image(directory / f"{name}.png", im)
            h, w = aligned.shape[:2]
            for q, spec in config["questions"].items():
                pts = (
                    list(spec["options"].values())
                    if spec["type"] == "choice"
                    else [p for c in spec["columns"] for p in c["digits"].values()]
                )
                x0 = max(0, int(min(p[0] for p in pts) * w) - 25)
                x1 = min(w, int(max(p[0] for p in pts) * w) + 25)
                y0 = max(0, int(min(p[1] for p in pts) * h) - 25)
                y1 = min(h, int(max(p[1] for p in pts) * h) + 25)
                write_image(directory / f"q{q}.png", aligned[y0:y1, x0:x1])
            (directory / "result.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        return result

    def analyze_file(self, path, debug_dir=None):
        results = []
        for i, image in enumerate(load_pages(path)):
            directory = Path(debug_dir) / f"page_{i + 1}" if debug_dir else None
            try:
                result = self.analyze(image, directory)
            except ValueError as exc:
                result = {"error": str(exc), "answers": {}, "subject": None}
            result["page"] = i + 1
            results.append(result)
        return results
