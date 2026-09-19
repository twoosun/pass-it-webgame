import cv2
import numpy as np
from .perspective import estimate_perspective


class AlignmentError(ValueError):
    pass


def feature_image(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return cv2.createCLAHE(2.0, (8, 8)).apply(gray)


def prepare_template(image):
    small = cv2.resize(image, (1263, 893))
    gray = feature_image(small)
    keypoints, descriptors = cv2.SIFT_create(nfeatures=5000).detectAndCompute(
        gray, None
    )
    return small, gray, keypoints, descriptors


def find_candidates(image, templates):
    factor = min(1.0, 1600 / max(image.shape[:2]))
    small = cv2.resize(image, None, fx=factor, fy=factor)
    kp, desc = cv2.SIFT_create(nfeatures=6500).detectAndCompute(
        feature_image(small), None
    )
    if desc is None:
        raise AlignmentError("OMR 정렬 실패: 문서의 인쇄 부분이 보이지 않습니다")
    candidates = []
    for subject, prepared in templates.items():
        _, gray, tkp, tdesc = prepared
        pairs = cv2.BFMatcher().knnMatch(desc, tdesc, k=2)
        matches = [
            a
            for pair in pairs
            if len(pair) == 2
            for a, b in [pair]
            if a.distance < 0.68 * b.distance
        ]
        # Repeated bubble digits must not vote many times for one template point.
        unique = {}
        for m in sorted(matches, key=lambda m: m.distance):
            unique.setdefault(m.trainIdx, m)
        matches = list(unique.values())
        if len(matches) < 20:
            continue
        src = np.float32([kp[m.queryIdx].pt for m in matches])
        dst = np.float32([tkp[m.trainIdx].pt for m in matches])
        try:
            H, inliers = estimate_perspective(src, dst)
        except ValueError:
            continue
        n = int(inliers.sum())
        if n < 16:
            continue
        projected = cv2.perspectiveTransform(src[inliers, None, :], H)[:, 0, :]
        error = float(np.median(np.linalg.norm(projected - dst[inliers], axis=1)))
        coverage = float(cv2.contourArea(cv2.convexHull(dst[inliers])) / (1263 * 893))
        corners = cv2.perspectiveTransform(
            np.float32(
                [
                    [
                        [0, 0],
                        [small.shape[1], 0],
                        [small.shape[1], small.shape[0]],
                        [0, small.shape[0]],
                    ]
                ]
            ),
            H,
        )[0]
        if not cv2.isContourConvex(corners) or coverage < 0.16:
            continue
        candidates.append(
            {
                "subject": subject,
                "H": H @ np.diag([factor, factor, 1]),
                "inliers": n,
                "error": error,
                "coverage": coverage,
                "rank": n * min(1.0, coverage / 0.5) / (1 + error),
            }
        )
    return sorted(candidates, key=lambda c: c["rank"], reverse=True)


def align_to_template(image, candidate, template, config):
    w, h = template.shape[1], template.shape[0]
    H = np.diag([w / 1263, h / 893, 1]) @ candidate["H"]
    warped = cv2.warpPerspective(image, H, (w, h), borderValue=(255, 255, 255))
    # Missing paper must not become synthetic white pixels read as BLANK.
    coverage_mask = cv2.warpPerspective(
        np.full(image.shape[:2], 255, np.uint8), H, (w, h), flags=cv2.INTER_NEAREST
    )
    points = [
        p for c in config["student_number"]["columns"] for p in c["digits"].values()
    ]
    for spec in config["questions"].values():
        points.extend(
            spec["options"].values()
            if spec["type"] == "choice"
            else [p for c in spec["columns"] for p in c["digits"].values()]
        )
    for x, y in points:
        cx, cy = round(x * w), round(y * h)
        patch = coverage_mask[
            max(0, cy - 14) : min(h, cy + 15), max(0, cx - 10) : min(w, cx + 11)
        ]
        if not patch.size or np.mean(patch == 255) < 0.99:
            raise AlignmentError(
                "OMR 정렬 실패: 날짜 또는 답안 영역이 잘렸습니다. 전체 답안지를 촬영하세요."
            )
    # Refine using print; additional handwriting is downweighted by the template mask.
    target = cv2.resize(cv2.cvtColor(template, cv2.COLOR_BGR2GRAY), (1263, 893))
    source = cv2.resize(cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY), (1263, 893))
    mask = (target < 240).astype("uint8") * 255
    correction = np.eye(2, 3, dtype=np.float32)
    ecc = None
    aligned = warped
    try:
        ecc, correction = cv2.findTransformECC(
            target,
            source,
            correction,
            cv2.MOTION_AFFINE,
            (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 45, 1e-5),
            mask,
            3,
        )
        if (
            np.max(np.abs(correction[:, :2] - np.eye(2))) < 0.012
            and np.max(np.abs(correction[:, 2])) < 5
        ):
            correction[:, 2] *= [w / 1263, h / 893]
            aligned = cv2.warpAffine(
                warped,
                correction,
                (w, h),
                flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                borderValue=(255, 255, 255),
            )
        else:
            ecc = None
    except cv2.error:
        pass
    # Independently verify black timing markers, avoiding a one-row repetitive-grid match.
    g = cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY)
    marker_scores = []
    for x, y in config["markers"]:
        cx, cy = round(x * w), round(y * h)
        patch = g[max(0, cy - 5) : cy + 6, max(0, cx - 3) : cx + 4]
        marker_scores.append(float(np.mean(patch < 150)) if patch.size else 0)
    marker_quality = (
        float(np.mean(np.array(marker_scores) > 0.45)) if marker_scores else 0
    )
    # Printed edge correspondence across the whole page.
    small = cv2.resize(g, (1263, 893))
    edge = cv2.Canny(small, 70, 180)
    distance = cv2.distanceTransform(255 - edge, cv2.DIST_L2, 3)
    reference = cv2.Canny(target, 70, 180) > 0
    edge_quality = float(np.mean(distance[reference] < 2.5))
    quality = float(
        np.clip(
            0.45 * marker_quality
            + 0.35 * edge_quality
            + 0.2 * min(1, candidate["coverage"] / 0.5),
            0,
            1,
        )
    )
    report = {k: candidate[k] for k in ("inliers", "error", "coverage")}
    report.update(
        quality=quality,
        markers=marker_quality,
        edges=edge_quality,
        ecc=float(ecc) if ecc else None,
    )
    if (
        candidate["inliers"] < 25
        or candidate["error"] > 2.5
        or marker_quality < 0.65
        or edge_quality < 0.55
        or quality < 0.7
    ):
        raise AlignmentError(
            f"OMR 정렬 실패: 다시 촬영하거나 여백과 기준 마커를 확인하세요 ({report})"
        )
    return warped, aligned, report, H
