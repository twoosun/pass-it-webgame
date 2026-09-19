import cv2


def all_points(config):
    for col, c in enumerate(config["student_number"]["columns"]):
        for d, p in c["digits"].items():
            yield f"D{col + 1}:{d}", p
    for q, spec in config["questions"].items():
        if spec["type"] == "choice":
            for a, p in spec["options"].items():
                yield f"Q{q}:{a}", p
        else:
            for col, c in enumerate(spec["columns"]):
                for d, p in c["digits"].items():
                    yield f"Q{q}.{col}:{d}", p


def overlay(image, config, result=None):
    out = image.copy()
    h, w = image.shape[:2]
    for label, p in all_points(config):
        center = (round(p[0] * w), round(p[1] * h))
        cv2.ellipse(out, center, (8, 12), 0, 0, 360, (220, 100, 20), 1)
        if label.startswith("D"):
            cv2.putText(
                out,
                label,
                (center[0] - 8, center[1] - 14),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.22,
                (0, 100, 230),
                1,
                cv2.LINE_AA,
            )
    if result:
        for q, spec in config["questions"].items():
            points = (
                list(spec["options"].values())
                if spec["type"] == "choice"
                else [p for col in spec["columns"] for p in col["digits"].values()]
            )
            x = min(p[0] for p in points) * w
            y = min(p[1] for p in points) * h
            r = result["answers"][q]
            color = (30, 130, 20) if r["status"] == "OK" else (0, 50, 220)
            cv2.putText(
                out,
                f"Q{q}={r['answer']} ({r['confidence']:.2f})",
                (int(x) - 30, int(y) - 16),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                color,
                1,
                cv2.LINE_AA,
            )
            if spec["type"] == "choice":
                for option, p in spec["options"].items():
                    score = r.get("scores", {}).get(option, 0)
                    center = (round(p[0] * w), round(p[1] * h))
                    cv2.putText(
                        out,
                        f"{score:.2f}",
                        (center[0] - 11, center[1] + 23),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.24,
                        color,
                        1,
                        cv2.LINE_AA,
                    )
    return out
