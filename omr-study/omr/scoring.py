import numpy as np


def calculate_confidence(best, second, quality, threshold):
    strength = np.clip((best - threshold) / 0.45, 0, 1)
    margin = np.clip((best - second) / 0.35, 0, 1)
    return round(float(quality * (0.45 * strength + 0.55 * margin)), 4)


def classify_scores(scores, quality=1.0, baseline=(0.0, 0.0)):
    ordered = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    key, best = ordered[0]
    second = ordered[1][1] if len(ordered) > 1 else 0.0
    threshold = max(0.20, baseline[0] + 5 * baseline[1])
    strong = [k for k, s in ordered if s >= threshold]
    confidence = calculate_confidence(best, second, quality, threshold)
    if best < max(0.065, baseline[0] + 2 * baseline[1]):
        answer, status = "BLANK", "BLANK"
        confidence = round(quality, 4)
    elif len(strong) > 1:
        answer, status = "MULTI", "MULTI"
        confidence = min(confidence, 0.49)
    elif (
        not strong
        or best - second < 0.12
        or best / max(second, 0.015) < 1.65
        or confidence < 0.55
    ):
        answer, status = "?", "UNKNOWN"
    else:
        answer, status = int(key), "OK"
    return {
        "answer": answer,
        "status": status,
        "confidence": confidence,
        "scores": {k: round(float(v), 4) for k, v in scores.items()},
    }
