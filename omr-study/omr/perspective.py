import cv2
import numpy as np


def estimate_perspective(source_points, target_points):
    """Use distributed printed features as document reference points."""
    if len(source_points) < 12:
        raise ValueError("OMR 정렬 실패: 특징점이 부족합니다")
    homography, mask = cv2.findHomography(
        np.float32(source_points),
        np.float32(target_points),
        cv2.RANSAC,
        3.0,
        maxIters=5000,
        confidence=0.999,
    )
    if homography is None or mask is None:
        raise ValueError("OMR 정렬 실패: 원근 변환을 계산하지 못했습니다")
    return homography, mask.ravel().astype(bool)
