from .alignment import find_candidates, AlignmentError


def detect_page_type(image, templates):
    candidates = find_candidates(image, templates)
    if not candidates:
        raise AlignmentError("OMR 정렬 실패: 지원하는 국어/수학/영어 답안지가 아닙니다")
    if len(candidates) > 1 and candidates[0]["rank"] < candidates[1]["rank"] * 1.15:
        raise AlignmentError(
            "과목 판별 불확실: 전체 답안지가 선명하게 보이도록 촬영하세요"
        )
    return candidates[0]
