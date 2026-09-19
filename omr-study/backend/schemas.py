from typing import Literal
from datetime import date
from pydantic import BaseModel, Field, ConfigDict


class Model(BaseModel):
    model_config = ConfigDict(
        extra="ignore", str_strip_whitespace=True, allow_inf_nan=False
    )


class Credentials(Model):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=8, max_length=200)
    username: str = Field(default="수험생", min_length=1, max_length=80)


class QuestionInput(Model):
    number: int = Field(ge=1, le=45)
    user_answer: str = "BLANK"
    correct_answer: str | None = None
    grading_status: Literal["CORRECT", "WRONG"] | None = None
    score_value: float | None = Field(default=None, ge=0, le=100)
    confidence: float = Field(default=1, ge=0, le=1)
    category: str = Field(default="", max_length=100)
    note: str = Field(default="", max_length=10000)
    review_status: Literal["미복습", "복습 중", "해결", "다시 볼 문제"] = "미복습"
    favorite: bool = False
    tags: list[str] = Field(default_factory=list, max_length=30)
    seconds: int | None = Field(default=None, ge=0)
    page: int | None = Field(default=None, ge=1)
    crop_file_id: str | None = None
    recognition: dict = Field(default_factory=dict)


class SubjectInput(Model):
    subject: Literal["korean", "math", "english"]
    raw_score: float | None = Field(default=None, ge=0, le=100)
    standard_score: float | None = Field(default=None, ge=0, le=300)
    percentile: float | None = Field(default=None, ge=0, le=100)
    grade: int | None = Field(default=None, ge=1, le=9)
    duration: float | None = Field(default=None, ge=0)
    first_pass: float | None = Field(default=None, ge=0)
    questions: list[QuestionInput] = Field(default_factory=list, max_length=45)


class ExamInput(Model):
    save_token: str | None = Field(default=None, min_length=16, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    round: str = Field(default="", max_length=100)
    exam_date: date | None = None
    date_needs_review: bool = False
    date_recognition: str = Field(default="", max_length=100)
    exam_type: str = Field(default="기타", max_length=100)
    memo: str = Field(default="", max_length=20000)
    state: Literal["DRAFT", "COMPLETED"] = "DRAFT"
    revision: int | None = None
    subjects: list[SubjectInput] = Field(default_factory=list, max_length=3)
    file_ids: list[str] = Field(default_factory=list, max_length=300)


class ReviewPatch(Model):
    note: str | None = Field(default=None, max_length=10000)
    review_status: Literal["미복습", "복습 중", "해결", "다시 볼 문제"] | None = None
    favorite: bool | None = None
    tags: list[str] | None = Field(default=None, max_length=30)
    category: str | None = Field(default=None, max_length=100)
    page: int | None = Field(default=None, ge=1)
