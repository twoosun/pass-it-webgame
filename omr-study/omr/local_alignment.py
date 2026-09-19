"""Refine each numeric grid using its printed structure, never the selected ink."""

import cv2
import numpy as np


def colored_structure(image):
    maximum = image.max(axis=2).astype(np.float32)
    minimum = image.min(axis=2).astype(np.float32)
    colored = (maximum - minimum) > np.maximum(18, 0.22 * maximum)
    return cv2.GaussianBlur(colored.astype(np.float32), (5, 5), 0)


def refine_numeric_grids(template, aligned, config):
    """Bounded affine correction accounts for page curl at the lower right.

    Evaluate a small translation pyramid to avoid repetitive-grid local minima.
    Reject large shifts, reflections, scale changes, or weak print correlation.
    """
    reference = colored_structure(template)
    observed = colored_structure(aligned)
    result = aligned.copy()
    height, width = reference.shape
    reports = {}
    for number, spec in config["questions"].items():
        if spec["type"] != "numeric":
            continue
        points = np.array(
            [p for col in spec["columns"] for p in col["digits"].values()]
        ) * [width, height]
        left, top = np.maximum(0, np.floor(points.min(axis=0) - [34, 25])).astype(int)
        right, bottom = np.minimum(
            [width, height], np.ceil(points.max(axis=0) + [34, 25])
        ).astype(int)
        target = reference[top:bottom, left:right]
        source = observed[top:bottom, left:right]
        if np.mean(source > 0.2) < 0.01:
            reports[number] = {"applied": False, "reason": "no_colored_print"}
            continue
        best = None
        corners = np.float32(
            [[0, 0], [right - left, 0], [right - left, bottom - top], [0, bottom - top]]
        )
        for dx, dy in [(0, 0), (10, 0), (20, 10), (-10, 0), (0, 10)]:
            warp = np.eye(2, 3, dtype=np.float32)
            warp[:, 2] = [dx, dy]
            try:
                correlation, warp = cv2.findTransformECC(
                    target,
                    source,
                    warp,
                    cv2.MOTION_AFFINE,
                    (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 80, 1e-5),
                    None,
                    5,
                )
            except cv2.error:
                continue
            moved = corners @ warp[:, :2].T + warp[:, 2]
            displacement = np.max(np.abs(moved - corners), axis=0)
            valid = (
                correlation > 0.60
                and displacement[0] < 42
                and displacement[1] < 32
                and np.max(np.abs(warp[:, :2] - np.eye(2))) < 0.10
            )
            if valid and (best is None or correlation > best[0]):
                best = (correlation, warp.copy(), displacement)
            if best is not None and best[0] > 0.94:
                break
        if best is None:
            reports[number] = {"applied": False, "reason": "weak_local_alignment"}
            continue
        correlation, warp, displacement = best
        source_image = aligned[top:bottom, left:right]
        corrected = cv2.warpAffine(
            source_image,
            warp,
            (right - left, bottom - top),
            flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
            borderMode=cv2.BORDER_REPLICATE,
        )
        # Only replace the grid interior; do not overwrite adjacent questions.
        result[top:bottom, left:right] = corrected
        reports[number] = {
            "applied": True,
            "correlation": round(float(correlation), 4),
            "max_displacement": displacement.round(2).tolist(),
        }
    return result, reports
