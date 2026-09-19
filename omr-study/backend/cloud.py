"""Signed direct uploads and one-page analysis for serverless deployments."""

from pathlib import Path
from uuid import uuid4
from typing import Literal
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from . import storage
from .database import StoredFile, Exam


class UploadTicket(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    size: int = Field(gt=0, le=storage.LIMIT)
    kind: Literal["original", "attachment", "backup-asset"] = "original"
    exam_id: str | None = None


class FileRequest(BaseModel):
    file_id: str


class PageRequest(FileRequest):
    page: int = Field(ge=1, le=30)


class ImportCheck(BaseModel):
    original_id: str = Field(min_length=1, max_length=200)


def page_count(path):
    if path.suffix.lower() == ".pdf":
        import pymupdf

        with pymupdf.open(path) as document:
            count = len(document)
            if document.needs_pass or not 1 <= count <= 30:
                raise ValueError("암호 없는 1~30페이지 PDF가 필요합니다")
            return count
    from PIL import Image

    with Image.open(path) as image:
        if image.width * image.height > 50_000_000:
            raise ValueError("이미지는 최대 50MP입니다")
        image.verify()
    return 1


def register_routes(app):
    from .main import (
        current_user,
        db_session,
        owned_exam,
        omr_engine,
        OMR_LOCK,
        persist_results,
    )

    def owned_file(file_id, user, db):
        file = db.query(StoredFile).filter_by(id=file_id, user_id=user.id).first()
        if not file or not file.path.startswith("supabase:"):
            raise HTTPException(404, "파일을 찾을 수 없습니다")
        return file

    @app.get("/api/config")
    def config():
        return {
            "direct_upload": storage.remote_enabled(),
            "max_file_bytes": storage.LIMIT,
        }

    @app.post("/api/import/check")
    def import_check(
        data: ImportCheck, user=Depends(current_user), db=Depends(db_session)
    ):
        from uuid import uuid5, NAMESPACE_URL

        restored_id = str(uuid5(NAMESPACE_URL, user.id + ":" + data.original_id))
        exists = (
            db.query(Exam.id)
            .filter(
                Exam.user_id == user.id, Exam.id.in_([data.original_id, restored_id])
            )
            .first()
            is not None
        )
        return {"exists": exists}

    @app.post("/api/uploads/sign")
    def sign(data: UploadTicket, user=Depends(current_user), db=Depends(db_session)):
        if not storage.remote_enabled():
            raise HTTPException(409, "외부 저장소가 연결되지 않았습니다")
        extension = Path(data.filename).suffix.lower()
        if extension not in (".pdf", ".png", ".jpg", ".jpeg"):
            raise HTTPException(422, "PDF/JPG/PNG 파일만 지원합니다")
        if data.kind == "attachment":
            if not data.exam_id:
                raise HTTPException(422, "시험 ID가 필요합니다")
            owned_exam(data.exam_id, user, db)
        elif data.exam_id:
            raise HTTPException(422, "첨부파일에만 시험 ID를 지정할 수 있습니다")
        file_id = str(uuid4())
        key = f"uploads/{user.id}/{file_id}/original{extension}"
        url = storage.signed_url(key, upload=True)
        record = StoredFile(
            id=file_id,
            user_id=user.id,
            filename=Path(data.filename).name,
            path="supabase:" + key,
            kind="pending:" + data.kind,
            exam_id=data.exam_id,
        )
        db.add(record)
        db.commit()
        return {"file_id": file_id, "upload_url": url}

    @app.post("/api/uploads/complete")
    def complete(data: FileRequest, user=Depends(current_user), db=Depends(db_session)):
        record = owned_file(data.file_id, user, db)
        if record.kind not in (
            "pending:original",
            "pending:attachment",
            "pending:backup-asset",
            "original",
            "attachment",
            "backup-asset",
        ):
            raise HTTPException(422, "업로드 원본이 아닙니다")
        try:
            with storage.materialize(record.path) as path:
                count = page_count(path)
        except (ValueError, OSError) as exc:
            raise HTTPException(
                422, "유효한 PDF/이미지가 아닙니다: " + str(exc)
            ) from exc
        record.kind = record.kind.removeprefix("pending:")
        db.commit()
        return {"id": record.id, "filename": record.filename, "pages": count}

    @app.post("/api/omr/analyze-page")
    def analyze_page(
        data: PageRequest, user=Depends(current_user), db=Depends(db_session)
    ):
        record = owned_file(data.file_id, user, db)
        if record.kind != "original":
            raise HTTPException(422, "업로드를 완료한 OMR 원본이 필요합니다")
        with storage.materialize(record.path) as path:
            debug = path.parent / "debug"
            try:
                from omr.io import read_page

                with OMR_LOCK:
                    image = read_page(path, data.page)
                    result = omr_engine().analyze(image, debug / f"page_{data.page}")
            except ValueError as exc:
                result = {"error": str(exc), "answers": {}, "subject": None}
            result["page"] = data.page
            return persist_results([result], debug, record, user, db)
