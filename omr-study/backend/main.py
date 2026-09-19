from pathlib import Path
from uuid import uuid4
from functools import lru_cache
import base64, csv, hashlib, hmac, io, json, os, secrets, time, threading
from fastapi import FastAPI, Depends, HTTPException, Request, Response, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .database import (
    SessionLocal,
    User,
    LoginSession,
    Exam,
    Subject,
    Question,
    StoredFile,
    DATA,
    ROOT,
)
from .schemas import Credentials, ExamInput, ReviewPatch
from .service import exam_json, question_json, update_exam, outcome

app = FastAPI(title="OMR Study", version="1.0.0")
OMR_LOCK = threading.Lock()


def db_session():
    with SessionLocal() as db:
        yield db


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def hash_password(password):
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return base64.b64encode(salt + key).decode()


def verify(password, stored):
    raw = base64.b64decode(stored)
    return hmac.compare_digest(
        raw[16:], hashlib.scrypt(password.encode(), salt=raw[:16], n=16384, r=8, p=1)
    )


@app.middleware("http")
async def same_origin(request, call_next):
    origin = request.headers.get("origin")
    allowed_origins = {str(request.base_url).rstrip("/")}
    public_origin = os.getenv("OMR_PUBLIC_ORIGIN", "").rstrip("/")
    if public_origin:
        allowed_origins.add(public_origin)
    if (
        request.method not in ("GET", "HEAD", "OPTIONS")
        and origin
        and origin.rstrip("/") not in allowed_origins
    ):
        return Response("Cross-origin write blocked", status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/health")
def health():
    return {"ok": True, "service": "omr-study"}


def current_user(request: Request, db=Depends(db_session)):
    token = request.cookies.get("omr_session", "")
    session = db.get(LoginSession, digest(token))
    if not session or session.expires < time.time():
        raise HTTPException(401, "로그인이 필요합니다")
    user = db.get(User, session.user_id)
    if not user:
        raise HTTPException(401, "로그인이 필요합니다")
    return user


def user_json(user):
    return {"id": user.id, "email": user.email, "username": user.username}


def login_cookie(user, response, db):
    token = secrets.token_urlsafe(32)
    db.add(
        LoginSession(
            token_hash=digest(token), user_id=user.id, expires=time.time() + 30 * 86400
        )
    )
    db.commit()
    response.set_cookie(
        "omr_session",
        token,
        httponly=True,
        samesite="strict",
        secure=os.getenv("OMR_HTTPS") == "1",
        max_age=30 * 86400,
    )


@app.post("/api/auth/register")
def register(data: Credentials, response: Response, db=Depends(db_session)):
    email = data.email.lower()
    if db.query(User).filter_by(email=email).first():
        raise HTTPException(409, "이미 사용 중인 아이디입니다")
    user = User(
        id=str(uuid4()),
        email=email,
        username=data.username,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    db.commit()
    login_cookie(user, response, db)
    return user_json(user)


@app.post("/api/auth/login")
def login(data: Credentials, response: Response, db=Depends(db_session)):
    user = db.query(User).filter_by(email=data.email.lower()).first()
    if not user or not verify(data.password, user.password_hash):
        raise HTTPException(401, "아이디 또는 비밀번호가 틀렸습니다")
    login_cookie(user, response, db)
    return user_json(user)


@app.post("/api/auth/logout")
def logout(request: Request, response: Response, db=Depends(db_session)):
    session = db.get(LoginSession, digest(request.cookies.get("omr_session", "")))
    if session:
        db.delete(session)
        db.commit()
    response.delete_cookie("omr_session")
    return {"ok": True}


@app.get("/api/auth/me")
def me(user=Depends(current_user)):
    return user_json(user)


@app.patch("/api/auth/me")
def change_user(
    data: dict, request: Request, user=Depends(current_user), db=Depends(db_session)
):
    if "username" in data:
        name = str(data["username"]).strip()
        if not 1 <= len(name) <= 80:
            raise HTTPException(422, "닉네임 길이를 확인하세요")
        user.username = name
    if data.get("password"):
        if not verify(str(data.get("old_password", "")), user.password_hash):
            raise HTTPException(403, "현재 비밀번호가 틀렸습니다")
        if not 8 <= len(str(data["password"])) <= 200:
            raise HTTPException(422, "비밀번호는 8~200자입니다")
        user.password_hash = hash_password(data["password"])
        db.query(LoginSession).filter(
            LoginSession.user_id == user.id,
            LoginSession.token_hash != digest(request.cookies.get("omr_session", "")),
        ).delete()
    db.commit()
    return user_json(user)


def owned_exam(exam_id, user, db):
    exam = db.query(Exam).filter_by(id=exam_id, user_id=user.id).first()
    if not exam:
        raise HTTPException(404, "시험을 찾을 수 없습니다")
    return exam


@app.get("/api/exams")
def exams(
    search: str = "",
    subject: str = "",
    exam_type: str = "",
    date_from: str = "",
    date_to: str = "",
    sort: str = "latest",
    user=Depends(current_user),
    db=Depends(db_session),
):
    query = db.query(Exam).filter_by(user_id=user.id)
    if search:
        query = query.filter(Exam.name.contains(search))
    if exam_type:
        query = query.filter_by(exam_type=exam_type)
    if date_from:
        query = query.filter(Exam.exam_date >= date_from)
    if date_to:
        query = query.filter(Exam.exam_date <= date_to)
    rows = [exam_json(e, db) for e in query.all()]
    if subject:
        rows = [e for e in rows if any(s["subject"] == subject for s in e["subjects"])]

    def key(e):
        if sort in ("korean", "math", "english"):
            return next(
                (
                    s["display_score"]
                    for s in e["subjects"]
                    if s["subject"] == sort and s["display_score"] is not None
                ),
                -1,
            )
        return e["name"] if sort == "name" else e["exam_date"]

    return sorted(rows, key=key, reverse=sort not in ("oldest", "name"))


@app.post("/api/exams")
def create_exam(payload: ExamInput, user=Depends(current_user), db=Depends(db_session)):
    duplicate = (
        db.query(Exam)
        .filter_by(
            user_id=user.id,
            name=payload.name,
            round=payload.round,
            exam_date=payload.exam_date.isoformat() if payload.exam_date else "",
        )
        .first()
    )
    e = Exam(id=str(uuid4()), user_id=user.id, created_at=time.time(), revision=1)
    db.add(e)
    update_exam(e, payload, db)
    db.commit()
    return {
        **exam_json(e, db),
        "warning": "비슷한 시험 기록이 이미 존재합니다." if duplicate else None,
    }


@app.get("/api/exams/{exam_id}")
def get_exam(exam_id: str, user=Depends(current_user), db=Depends(db_session)):
    return exam_json(owned_exam(exam_id, user, db), db)


@app.put("/api/exams/{exam_id}")
def put_exam(
    exam_id: str, payload: ExamInput, user=Depends(current_user), db=Depends(db_session)
):
    e = owned_exam(exam_id, user, db)
    if payload.revision is not None and payload.revision != e.revision:
        raise HTTPException(409, "다른 창에서 수정되었습니다. 다시 불러오세요.")
    update_exam(e, payload, db)
    e.revision += 1
    db.commit()
    return exam_json(e, db)


@app.delete("/api/exams/{exam_id}")
def delete_exam(exam_id: str, user=Depends(current_user), db=Depends(db_session)):
    e = owned_exam(exam_id, user, db)
    files = db.query(StoredFile).filter_by(exam_id=e.id, user_id=user.id).all()
    paths = [f.path for f in files]
    for f in files:
        db.delete(f)
    db.delete(e)
    db.commit()
    for path in paths:
        p = (DATA / path).resolve()
        if p.is_relative_to(DATA.resolve()):
            p.unlink(missing_ok=True)
    return {"ok": True}


def owned_question(qid, user, db):
    q = (
        db.query(Question)
        .join(Subject)
        .join(Exam)
        .filter(Question.id == qid, Exam.user_id == user.id)
        .first()
    )
    if not q:
        raise HTTPException(404, "문항을 찾을 수 없습니다")
    return q


@app.get("/api/wrong-answers")
def wrong_answers(
    subject: str = "",
    exam_id: str = "",
    status: str = "",
    tag: str = "",
    favorite: bool = False,
    date_from: str = "",
    date_to: str = "",
    retry: bool = False,
    user=Depends(current_user),
    db=Depends(db_session),
):
    result = []
    for q in (
        db.query(Question)
        .join(Subject)
        .join(Exam)
        .filter(Exam.user_id == user.id)
        .all()
    ):
        s = q.subject_record
        e = s.exam
        if outcome(q) != "WRONG":
            continue
        if (
            subject
            and s.subject != subject
            or exam_id
            and e.id != exam_id
            or status
            and q.review_status != status
        ):
            continue
        if tag and tag not in q.tags or favorite and not q.favorite:
            continue
        if date_from and e.exam_date < date_from or date_to and e.exam_date > date_to:
            continue
        if retry and not (q.favorite or q.review_status in ("미복습", "다시 볼 문제")):
            continue
        result.append(
            {
                **question_json(q),
                "subject": s.subject,
                "exam_id": e.id,
                "exam_name": e.name,
                "round": e.round,
                "exam_date": e.exam_date,
            }
        )
    return sorted(result, key=lambda q: (q["exam_date"], q["number"]), reverse=True)


@app.get("/api/wrong-answers/{qid}")
def get_wrong(qid: str, user=Depends(current_user), db=Depends(db_session)):
    q = owned_question(qid, user, db)
    s = q.subject_record
    e = s.exam
    attachments = (
        db.query(StoredFile)
        .filter_by(exam_id=e.id, user_id=user.id, kind="attachment")
        .all()
    )
    return {
        **question_json(q),
        "subject": s.subject,
        "exam_id": e.id,
        "exam_name": e.name,
        "round": e.round,
        "attachments": [{"id": f.id, "filename": f.filename} for f in attachments],
    }


@app.patch("/api/wrong-answers/{qid}")
def patch_wrong(
    qid: str, payload: ReviewPatch, user=Depends(current_user), db=Depends(db_session)
):
    q = owned_question(qid, user, db)
    for k, v in payload.model_dump(exclude_unset=True).items():
        if v is not None or k == "page":
            setattr(q, k, v)
    q.subject_record.exam.revision += 1
    db.commit()
    return question_json(q)


@lru_cache(maxsize=1)
def omr_engine():
    from omr import OMREngine

    return OMREngine()


def save_file(path, user, db, kind, filename=None, exam_id=None):
    f = StoredFile(
        id=str(uuid4()),
        user_id=user.id,
        exam_id=exam_id,
        filename=filename or path.name,
        path=path.relative_to(DATA).as_posix(),
        kind=kind,
    )
    db.add(f)
    return f


def receive_file(file, user, db, kind):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in (".pdf", ".png", ".jpg", ".jpeg"):
        raise HTTPException(422, "PDF/JPG/PNG 파일만 지원합니다")
    directory = DATA / "uploads" / user.id / str(uuid4())
    directory.mkdir(parents=True)
    path = directory / ("original" + suffix)
    size = 0
    with path.open("wb") as out:
        while chunk := file.file.read(1024 * 1024):
            size += len(chunk)
            if size > 30 * 1024 * 1024:
                out.close()
                path.unlink(missing_ok=True)
                raise HTTPException(413, "최대 30MB입니다")
            out.write(chunk)
    if size == 0:
        raise HTTPException(422, "빈 파일입니다")
    return path, save_file(path, user, db, kind, Path(file.filename).name)


@app.post("/api/omr/analyze")
def analyze(
    file: UploadFile = File(...), user=Depends(current_user), db=Depends(db_session)
):
    path, original = receive_file(file, user, db, "original")
    try:
        with OMR_LOCK:
            results = omr_engine().analyze_file(path, path.parent / "debug")
    except Exception as exc:
        raise HTTPException(422, f"파일을 분석할 수 없습니다: {exc}") from exc
    all_files = [original.id]
    for i, result in enumerate(results):
        result["files"] = {}
        directory = path.parent / "debug" / f"page_{i + 1}"
        for image in directory.glob("*.png"):
            f = save_file(
                image,
                user,
                db,
                "crop"
                if image.stem.startswith("q") and image.stem[1:].isdigit()
                else "debug",
            )
            result["files"][image.stem] = f.id
            all_files.append(f.id)
        for q, r in result.get("answers", {}).items():
            r["crop_file_id"] = result["files"].get("q" + q)
    db.commit()
    return {"pages": results, "file_ids": all_files}


@app.post("/api/exams/{exam_id}/attachments")
def attachment(
    exam_id: str,
    file: UploadFile = File(...),
    user=Depends(current_user),
    db=Depends(db_session),
):
    owned_exam(exam_id, user, db)
    _, f = receive_file(file, user, db, "attachment")
    f.exam_id = exam_id
    db.commit()
    return {"id": f.id, "filename": f.filename}


@app.get("/api/files/{file_id}")
def file_content(file_id: str, user=Depends(current_user), db=Depends(db_session)):
    f = db.query(StoredFile).filter_by(id=file_id, user_id=user.id).first()
    if not f:
        raise HTTPException(404, "파일을 찾을 수 없습니다")
    path = (DATA / f.path).resolve()
    if not path.is_relative_to(DATA.resolve()) or not path.is_file():
        raise HTTPException(404, "파일을 찾을 수 없습니다")
    return FileResponse(path, filename=f.filename, content_disposition_type="inline")


@app.get("/api/stats")
def stats(
    subject: str = "math",
    exam_type: str = "",
    user=Depends(current_user),
    db=Depends(db_session),
):
    records = exams(
        subject=subject, exam_type=exam_type, sort="oldest", user=user, db=db
    )
    series = []
    repeats = {}
    categories = {}
    counts = {
        k: 0 for k in ("CORRECT", "WRONG", "BLANK", "MULTI", "UNKNOWN", "UNGRADED")
    }
    for e in records:
        s = next(s for s in e["subjects"] if s["subject"] == subject)
        series.append(
            {
                "id": e["id"],
                "date": e["exam_date"],
                "name": e["name"],
                **{
                    k: s[k]
                    for k in (
                        "display_score",
                        "standard_score",
                        "percentile",
                        "grade",
                        "accuracy",
                    )
                },
            }
        )
        for q in s["questions"]:
            counts[q["outcome"]] += 1
            if q["outcome"] not in ("CORRECT", "WRONG"):
                continue
            c = categories.setdefault(
                q["category"] or "미지정", {"total": 0, "correct": 0, "wrong": 0}
            )
            c["total"] += 1
            c["correct"] += q["outcome"] == "CORRECT"
            c["wrong"] += q["outcome"] != "CORRECT"
    for e in records[-10:]:
        for s in e["subjects"]:
            if s["subject"] != subject:
                continue
            for q in s["questions"]:
                if q["outcome"] not in ("CORRECT", "WRONG"):
                    continue
                r = repeats.setdefault(q["number"], {"total": 0, "wrong": 0})
                r["total"] += 1
                r["wrong"] += q["outcome"] != "CORRECT"
    scores = [p["display_score"] for p in series if p["display_score"] is not None]
    avg = lambda n: round(sum(scores[-n:]) / len(scores[-n:]), 2) if scores else None
    wrong = wrong_answers(subject=subject, user=user, db=db)
    return {
        "series": series,
        "count": len(records),
        "average5": avg(5),
        "average10": avg(10),
        "max": max(scores) if scores else None,
        "min": min(scores) if scores else None,
        "counts": counts,
        "categories": categories,
        "repeated": repeats,
        "unreviewed": sum(q["review_status"] == "미복습" for q in wrong),
    }


@app.get("/api/export")
def export(
    format: str = "json",
    subject: str = "",
    wrong_only: bool = False,
    user=Depends(current_user),
    db=Depends(db_session),
):
    records = exams(user=user, db=db)
    if format == "json":
        ids = {fid for e in records for fid in e["file_ids"]}
        files = []
        for f in db.query(StoredFile).filter_by(user_id=user.id).all():
            if f.id not in ids:
                continue
            path = (DATA / f.path).resolve()
            if path.is_relative_to(DATA.resolve()) and path.is_file():
                files.append(
                    {
                        "id": f.id,
                        "filename": f.filename,
                        "kind": f.kind,
                        "extension": path.suffix,
                        "data": base64.b64encode(path.read_bytes()).decode(),
                    }
                )
        return {"version": 1, "exams": records, "files": files}
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "date",
            "exam",
            "round",
            "subject",
            "question",
            "answer",
            "correct",
            "outcome",
            "score",
            "note",
            "tags",
        ]
    )
    safe = lambda v: (
        "'" + v
        if isinstance(v, str) and v.startswith(("=", "+", "-", "@", "\t", "\r"))
        else v
    )
    for e in records:
        for s in e["subjects"]:
            if subject and subject != s["subject"]:
                continue
            for q in s["questions"]:
                if wrong_only and (q["outcome"] != "WRONG"):
                    continue
                writer.writerow(
                    [
                        safe(v)
                        for v in [
                            e["exam_date"],
                            e["name"],
                            e["round"],
                            s["subject"],
                            q["number"],
                            q["user_answer"],
                            q["correct_answer"],
                            q["outcome"],
                            q["score_value"],
                            q["note"],
                            ",".join(q["tags"]),
                        ]
                    ]
                )
    return Response(
        "\ufeff" + output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="omr-records.csv"'},
    )


@app.post("/api/import")
def import_backup(data: dict, user=Depends(current_user), db=Depends(db_session)):
    if (
        data.get("version") != 1
        or not isinstance(data.get("exams"), list)
        or len(data["exams"]) > 1000
    ):
        raise HTTPException(422, "지원하지 않는 백업입니다")
    added = 0
    skipped = 0
    file_payloads = {
        str(f.get("id")): f for f in data.get("files", []) if isinstance(f, dict)
    }
    restored_files = {}
    total_bytes = 0
    for row in data["exams"]:
        # Stable per-user UUID prevents duplicates without allowing cross-user overwrite.
        from uuid import uuid5, NAMESPACE_URL

        original = str(row.get("id", ""))
        if not original:
            raise HTTPException(422, "백업 시험 ID가 필요합니다")
        eid = str(uuid5(NAMESPACE_URL, user.id + ":" + original))
        if (
            db.query(Exam)
            .filter(Exam.user_id == user.id, Exam.id.in_([original, eid]))
            .first()
        ):
            skipped += 1
            continue
        clean = json.loads(json.dumps(row))
        if not clean.get("exam_date"):
            clean["exam_date"] = None
        clean["file_ids"] = []
        for old_file_id in row.get("file_ids", []):
            if old_file_id in restored_files:
                clean["file_ids"].append(restored_files[old_file_id])
                continue
            entry = file_payloads.get(old_file_id)
            if not entry:
                continue
            extension = entry.get("extension", "").lower()
            if extension not in (".png", ".jpg", ".jpeg", ".pdf"):
                raise HTTPException(422, "허용되지 않는 백업 파일 형식")
            try:
                raw = base64.b64decode(entry.get("data", ""), validate=True)
            except Exception as exc:
                raise HTTPException(422, "잘못된 백업 파일 데이터") from exc
            total_bytes += len(raw)
            if len(raw) > 30 * 1024 * 1024 or total_bytes > 500 * 1024 * 1024:
                raise HTTPException(413, "복구 파일 용량 제한 초과")
            directory = DATA / "uploads" / user.id / str(uuid4())
            directory.mkdir(parents=True)
            path = directory / ("restored" + extension)
            path.write_bytes(raw)
            f = save_file(
                path,
                user,
                db,
                entry.get("kind", "attachment"),
                Path(entry.get("filename", "restored" + extension)).name,
            )
            restored_files[old_file_id] = f.id
            clean["file_ids"].append(f.id)
        for s in clean.get("subjects", []):
            for q in s.get("questions", []):
                q["crop_file_id"] = restored_files.get(q.get("crop_file_id"))
        try:
            payload = ExamInput.model_validate(clean)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        e = Exam(id=eid, user_id=user.id, created_at=time.time(), revision=1)
        db.add(e)
        update_exam(e, payload, db)
        added += 1
    db.commit()
    return {
        "added": added,
        "skipped": skipped,
        "note": "답안, 복습 기록 및 첨부파일 복원 완료.",
    }


frontend = ROOT / "frontend/dist"
if frontend.exists():
    app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        return FileResponse(frontend / "index.html")
