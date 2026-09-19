from fastapi.testclient import TestClient
from tests.test_web import register, payload
from backend.main import app


def test_manual_grading_without_any_answer_key():
    client = TestClient(app)
    register(client, "manual-grades")
    data = payload()
    for q in data["subjects"][0]["questions"]:
        q["user_answer"] = "?"
        q["grading_status"] = "CORRECT"
        q["score_value"] = 4
    r = client.post("/api/exams", json=data)
    assert r.status_code == 200, r.text
    exam = r.json()
    subject = exam["subjects"][0]
    assert subject["display_score"] == 100
    assert subject["correct_count"] == 30
    assert all(
        q["score_value"] is None and q["correct_answer"] is None
        for q in subject["questions"]
    )
    assert client.get("/api/wrong-answers").json() == []
    subject["questions"][15]["grading_status"] = "WRONG"
    subject["questions"][15]["score_value"] = None
    r = client.put("/api/exams/" + exam["id"], json=exam)
    assert r.status_code == 200, r.text
    exam = r.json()
    assert exam["subjects"][0]["display_score"] is None
    assert exam["subjects"][0]["missing_points"] == [16]
    wrong = client.get("/api/wrong-answers").json()
    assert len(wrong) == 1 and wrong[0]["number"] == 16
    assert wrong[0]["recognition_status"] == "UNKNOWN"
    exam["subjects"][0]["questions"][15]["score_value"] = 4
    exam["subjects"][0]["raw_score"] = (
        1  # old manual raw score cannot override deductions
    )
    r = client.put("/api/exams/" + exam["id"], json=exam)
    assert r.status_code == 200, r.text
    exam = r.json()
    assert exam["subjects"][0]["display_score"] == 96
    assert client.get("/api/stats?subject=math").json()["average5"] == 96
    backup = client.get("/api/export").json()
    other = TestClient(app)
    register(other, "manual-restore")
    assert other.post("/api/import", json=backup).status_code == 200
    assert other.get("/api/exams").json()[0]["subjects"][0]["display_score"] == 96


def test_incomplete_grading_and_excess_deductions():
    c = TestClient(app)
    register(c, "grade-validation")
    data = payload()
    for q in data["subjects"][0]["questions"]:
        q["grading_status"] = "WRONG"
        q["score_value"] = 4
    assert c.post("/api/exams", json=data).status_code == 422
    data = payload()
    data["subjects"][0]["questions"][0]["grading_status"] = None
    r = c.post("/api/exams", json=data)
    assert r.status_code == 200, r.text
    assert r.json()["subjects"][0]["display_score"] is None
    assert r.json()["subjects"][0]["ungraded_count"] == 1


def test_date_error_requires_user_correction():
    c = TestClient(app)
    register(c, "date-correction")
    data = payload()
    data.update(exam_date=None, date_needs_review=True, date_recognition="2026-0?17")
    assert c.post("/api/exams", json=data).status_code == 422
    data["state"] = "DRAFT"
    r = c.post("/api/exams", json=data)
    assert r.status_code == 200, r.text
    exam = r.json()
    assert exam["exam_date"] == "" and exam["date_needs_review"]
    other = TestClient(app)
    register(other, "draft-date-restore")
    restored = other.post("/api/import", json=c.get("/api/export").json())
    assert restored.status_code == 200, restored.text
    assert other.get("/api/exams").json()[0]["date_needs_review"]
    exam.update(state="COMPLETED", exam_date="2026-09-17", date_needs_review=False)
    r = c.put("/api/exams/" + exam["id"], json=exam)
    assert r.status_code == 200, r.text
    assert r.json()["exam_date"] == "2026-09-17"
