from uuid import uuid4
from fastapi import HTTPException
from .database import Subject, Question, StoredFile


def numeric(subject, number):
    return subject == "math" and (16 <= number <= 22 or number >= 29)


def outcome(q):
    if q.grading_status is not None:
        return q.grading_status
    # Old records and backups remain readable; new UI does not require a key.
    if q.correct_answer is not None:
        return "CORRECT" if q.user_answer == q.correct_answer else "WRONG"
    return "UNGRADED"


def question_json(q):
    result = {
        field: getattr(q, field)
        for field in (
            "id",
            "number",
            "user_answer",
            "correct_answer",
            "grading_status",
            "score_value",
            "confidence",
            "category",
            "note",
            "review_status",
            "favorite",
            "tags",
            "seconds",
            "page",
            "crop_file_id",
            "recognition",
        )
    }
    result["outcome"] = outcome(q)
    result["grading_status"] = (
        result["outcome"] if result["outcome"] in ("CORRECT", "WRONG") else None
    )
    result["recognition_status"] = q.recognition.get(
        "status",
        "UNKNOWN"
        if q.user_answer == "?"
        else q.user_answer
        if q.user_answer in ("BLANK", "MULTI")
        else "OK",
    )
    result["type"] = (
        "numeric" if numeric(q.subject_record.subject, q.number) else "choice"
    )
    return result


def subject_json(s):
    questions = [question_json(q) for q in sorted(s.questions, key=lambda q: q.number)]
    graded = [q for q in questions if q["outcome"] in ("CORRECT", "WRONG")]
    correct = sum(q["outcome"] == "CORRECT" for q in graded)
    count = 30 if s.subject == "math" else 45
    wrong = [q for q in graded if q["outcome"] == "WRONG"]
    missing_points = [q["number"] for q in wrong if q["score_value"] is None]
    complete = len(graded) == count and not missing_points
    deduction = sum(q["score_value"] or 0 for q in wrong)
    auto = 100 - deduction if complete else None
    return {
        **{
            k: getattr(s, k)
            for k in (
                "id",
                "subject",
                "raw_score",
                "standard_score",
                "percentile",
                "grade",
                "duration",
                "first_pass",
            )
        },
        "questions": questions,
        "auto_score": auto,
        "display_score": auto,
        "deduction": deduction,
        "ungraded_count": count - len(graded),
        "missing_points": missing_points,
        "correct_count": correct,
        "graded_count": len(graded),
        "accuracy": round(correct / len(graded) * 100, 2) if graded else None,
        "wrong_count": sum(q["outcome"] != "CORRECT" for q in graded),
    }


def exam_json(e, db, files=None):
    if files is None:
        files = db.query(StoredFile).filter_by(exam_id=e.id, user_id=e.user_id).all()
    return {
        **{
            k: getattr(e, k)
            for k in (
                "id",
                "save_token",
                "name",
                "round",
                "exam_date",
                "exam_type",
                "memo",
                "state",
                "created_at",
                "revision",
                "date_needs_review",
                "date_recognition",
            )
        },
        "subjects": [subject_json(s) for s in e.subjects],
        "file_ids": [f.id for f in files],
        "files": [{"id": f.id, "filename": f.filename, "kind": f.kind} for f in files],
    }


def normalize_answer(answer, is_numeric, key=False):
    if answer is None or (key and answer == ""):
        return None
    s = str(answer).strip()
    if not key and s in ("BLANK", "MULTI", "?", "UNKNOWN"):
        return "?" if s == "UNKNOWN" else s
    if not s.isascii() or not s.isdigit():
        raise HTTPException(422, "답안은 숫자 또는 BLANK/MULTI/?여야 합니다")
    value = int(s)
    if not (0 <= value <= 999 if is_numeric else 1 <= value <= 5):
        raise HTTPException(422, "문항 유형에 맞지 않는 답안입니다")
    return str(value)


def update_exam(e, payload, db):
    if payload.state == "COMPLETED" and (
        payload.exam_date is None or payload.date_needs_review
    ):
        raise HTTPException(422, "OMR 날짜를 확인하고 시험 날짜를 직접 입력하세요.")
    subjects = [s.subject for s in payload.subjects]
    if len(set(subjects)) != len(subjects):
        raise HTTPException(422, "과목 중복")

    # Populate required exam fields before any query can trigger autoflush for
    # a newly created record.
    for k in ("name", "round", "exam_type", "memo", "state"):
        setattr(e, k, getattr(payload, k))
    e.exam_date = payload.exam_date.isoformat() if payload.exam_date else ""
    e.date_needs_review = payload.date_needs_review
    e.date_recognition = payload.date_recognition

    # OMR records can contain hundreds of crop references. Fetch them in one
    # query instead of issuing one remote database round trip per question.
    requested_file_ids = set(payload.file_ids)
    requested_file_ids.update(
        q.crop_file_id
        for subject in payload.subjects
        for q in subject.questions
        if q.crop_file_id
    )
    files_by_id = (
        {
            file.id: file
            for file in db.query(StoredFile)
            .filter(StoredFile.id.in_(requested_file_ids))
            .all()
        }
        if requested_file_ids
        else {}
    )
    existing = {s.subject: s for s in e.subjects}
    for src in payload.subjects:
        subject = existing.get(src.subject)
        if subject is None:
            subject = Subject(id=str(uuid4()), subject=src.subject)
            e.subjects.append(subject)
        for k in (
            "raw_score",
            "standard_score",
            "percentile",
            "grade",
            "duration",
            "first_pass",
        ):
            setattr(subject, k, getattr(src, k))
        old = {q.number: q for q in subject.questions}
        seen = set()
        for q in src.questions:
            if q.number in seen or q.number > (30 if src.subject == "math" else 45):
                raise HTTPException(422, "문항 번호 중복/범위 오류")
            seen.add(q.number)
            target = old.get(q.number)
            if target is None:
                target = Question(id=str(uuid4()), number=q.number)
                subject.questions.append(target)
            fields = q.model_dump()
            fields["user_answer"] = normalize_answer(
                q.user_answer, numeric(src.subject, q.number)
            )
            fields["correct_answer"] = normalize_answer(
                q.correct_answer, numeric(src.subject, q.number), True
            )
            if q.grading_status == "CORRECT":
                fields["score_value"] = None
            if q.crop_file_id:
                f = files_by_id.get(q.crop_file_id)
                if (
                    not f
                    or f.kind.startswith("pending:")
                    or f.user_id != e.user_id
                    or f.exam_id not in (None, e.id)
                ):
                    raise HTTPException(422, "다른 기록의 이미지입니다")
                f.exam_id = e.id
            for key, value in fields.items():
                setattr(target, key, value)
        # A slow or interrupted client can submit a partial snapshot. Missing
        # subjects/questions are preserved; deletion is only performed by the
        # dedicated delete endpoint.
        if (
            sum(q.score_value or 0 for q in subject.questions if outcome(q) == "WRONG")
            > 100
        ):
            raise HTTPException(422, "오답 배점 합계는 100점을 넘을 수 없습니다.")
    for file_id in payload.file_ids:
        f = files_by_id.get(file_id)
        if (
            not f
            or f.kind.startswith("pending:")
            or f.user_id != e.user_id
            or f.exam_id not in (None, e.id)
        ):
            raise HTTPException(422, "첨부파일을 찾을 수 없습니다")
        f.exam_id = e.id
