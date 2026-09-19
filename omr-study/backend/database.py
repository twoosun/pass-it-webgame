from pathlib import Path
import os
from sqlalchemy import (
    create_engine,
    String,
    Text,
    Float,
    Integer,
    ForeignKey,
    JSON,
    Boolean,
    inspect,
    text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("OMR_DATA_DIR", ROOT / "data"))
DATA.mkdir(parents=True, exist_ok=True)
url = os.environ.get("DATABASE_URL", f"sqlite:///{(DATA / 'app.db').as_posix()}")
engine = create_engine(
    url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {}
)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True)
    username: Mapped[str] = mapped_column(String)
    password_hash: Mapped[str] = mapped_column(String)


class LoginSession(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    expires: Mapped[float] = mapped_column(Float)


class Exam(Base):
    __tablename__ = "exams"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    round: Mapped[str] = mapped_column(String, default="")
    exam_date: Mapped[str] = mapped_column(String)
    exam_type: Mapped[str] = mapped_column(String, default="기타")
    memo: Mapped[str] = mapped_column(Text, default="")
    state: Mapped[str] = mapped_column(String, default="DRAFT")
    created_at: Mapped[float] = mapped_column(Float)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    date_needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    date_recognition: Mapped[str] = mapped_column(String, default="")
    subjects: Mapped[list["Subject"]] = relationship(
        cascade="all, delete-orphan", back_populates="exam"
    )


class Subject(Base):
    __tablename__ = "subjects"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    exam_id: Mapped[str] = mapped_column(ForeignKey("exams.id"), index=True)
    subject: Mapped[str] = mapped_column(String)
    raw_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    standard_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    percentile: Mapped[float | None] = mapped_column(Float, nullable=True)
    grade: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    first_pass: Mapped[float | None] = mapped_column(Float, nullable=True)
    exam: Mapped[Exam] = relationship(back_populates="subjects")
    questions: Mapped[list["Question"]] = relationship(
        cascade="all, delete-orphan", back_populates="subject_record"
    )


class Question(Base):
    __tablename__ = "questions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    subject_id: Mapped[str] = mapped_column(ForeignKey("subjects.id"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    user_answer: Mapped[str] = mapped_column(String, default="BLANK")
    correct_answer: Mapped[str | None] = mapped_column(String, nullable=True)
    grading_status: Mapped[str | None] = mapped_column(String, nullable=True)
    score_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1)
    category: Mapped[str] = mapped_column(String, default="")
    note: Mapped[str] = mapped_column(Text, default="")
    review_status: Mapped[str] = mapped_column(String, default="미복습")
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    crop_file_id: Mapped[str | None] = mapped_column(String, nullable=True)
    recognition: Mapped[dict] = mapped_column(JSON, default=dict)
    subject_record: Mapped[Subject] = relationship(back_populates="questions")


class StoredFile(Base):
    __tablename__ = "omr_files"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    exam_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    filename: Mapped[str] = mapped_column(String)
    path: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)


Base.metadata.create_all(engine)


def migrate_manual_grading():
    """Additive migration preserves existing accounts, answers, and attachments."""
    inspector = inspect(engine)
    additions = {
        "questions": {"grading_status": "VARCHAR"},
        "exams": {
            "date_needs_review": "BOOLEAN DEFAULT FALSE",
            "date_recognition": "VARCHAR DEFAULT ''",
        },
    }
    with engine.begin() as connection:
        for table, fields in additions.items():
            existing = {column["name"] for column in inspector.get_columns(table)}
            for name, definition in fields.items():
                if name not in existing:
                    connection.execute(
                        text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
                    )


migrate_manual_grading()
