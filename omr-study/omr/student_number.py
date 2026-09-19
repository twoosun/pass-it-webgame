from datetime import date
from .scoring import classify_scores


def validate_date(raw):
    try:
        if len(raw) != 8 or not raw.isdigit():
            raise ValueError()
        value = date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
        return value.isoformat(), None
    except ValueError:
        return None, "유효하지 않거나 불확실한 날짜입니다. 판독값을 확인하세요."


def read_virtual_student_number(columns, quality, baseline):
    digits = [classify_scores(c, quality, baseline) for c in columns]
    raw = "".join(
        str(d["answer"]) if isinstance(d["answer"], int) else "?" for d in digits
    )
    iso, warning = validate_date(raw)
    return {
        "raw": raw,
        "display": raw[:4] + "-" + raw[4:],
        "iso": iso,
        "warning": warning,
        "digits": digits,
    }
