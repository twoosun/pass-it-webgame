import os, tempfile

os.environ["OMR_DATA_DIR"] = tempfile.mkdtemp(prefix="omr-api-test-")
from fastapi.testclient import TestClient
from backend.main import app
from backend.database import SessionLocal, User
from omr.io import ROOT


def register(client, email):
    r = client.post(
        "/api/auth/register",
        json={"email": email, "password": "strong-test-password", "username": "테스트"},
    )
    assert r.status_code == 200, r.text
    return r.json()


def payload():
    return {
        "name": "이해원 시즌2",
        "round": "3회",
        "exam_date": "2026-09-19",
        "state": "COMPLETED",
        "subjects": [
            {
                "subject": "math",
                "questions": [
                    {
                        "number": i,
                        "user_answer": "1",
                        "grading_status": "CORRECT" if i != 21 else "WRONG",
                        "score_value": None if i != 21 else 3,
                    }
                    for i in range(1, 31)
                ],
            }
        ],
    }


def test_repeated_create_with_same_save_token_is_idempotent():
    client = TestClient(app)
    register(client, "idempotent-save")
    data = payload()
    data["save_token"] = "save-token-1234567890"
    first = client.post("/api/exams", json=data)
    second = client.post("/api/exams", json=data)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json()["id"] == first.json()["id"]
    assert len(client.get("/api/exams").json()) == 1


def test_partial_update_does_not_delete_existing_questions():
    client = TestClient(app)
    register(client, "partial-save")
    created = client.post("/api/exams", json=payload()).json()
    partial = {**created, "subjects": [{**created["subjects"][0], "questions": created["subjects"][0]["questions"][:1]}]}
    response = client.put("/api/exams/" + created["id"], json=partial)
    assert response.status_code == 200, response.text
    assert len(response.json()["subjects"][0]["questions"]) == 30


def test_full_record_lifecycle_and_isolation():
    a = TestClient(app)
    b = TestClient(app)
    assert a.get("/api/exams").status_code == 401
    user = register(a, "student-a")
    register(b, "student-b")
    with SessionLocal() as db:
        assert db.get(User, user["id"]).password_hash != "strong-test-password"
    data = payload()
    r = a.post("/api/exams", json=data)
    assert r.status_code == 200, r.text
    e = r.json()
    eid = e["id"]
    assert e["subjects"][0]["auto_score"] == 97
    assert b.get("/api/exams/" + eid).status_code == 404
    assert b.delete("/api/exams/" + eid).status_code == 404
    wrong = a.get("/api/wrong-answers").json()
    assert len(wrong) == 1
    assert wrong[0]["number"] == 21
    qid = wrong[0]["id"]
    assert (
        b.patch("/api/wrong-answers/" + qid, json={"note": "intrusion"}).status_code
        == 404
    )
    assert (
        a.patch(
            "/api/wrong-answers/" + qid,
            json={
                "review_status": "해결",
                "tags": ["시간 부족"],
                "note": "조건 누락",
                "favorite": True,
            },
        ).status_code
        == 200
    )
    assert (
        a.get("/api/wrong-answers?status=해결&tag=시간%20부족&favorite=true").json()[0][
            "id"
        ]
        == qid
    )
    stats = a.get("/api/stats?subject=math").json()
    assert stats["average5"] == 97
    assert stats["counts"]["WRONG"] == 1
    e = a.get("/api/exams/" + eid).json()
    e["subjects"][0]["questions"][20]["user_answer"] = "2"
    e["subjects"][0]["questions"][20]["grading_status"] = "CORRECT"
    r = a.put("/api/exams/" + eid, json=e)
    assert r.status_code == 200, r.text
    assert a.get("/api/wrong-answers").json() == []
    assert a.put("/api/exams/" + eid, json=e).status_code == 409
    backup = a.get("/api/export").json()
    assert a.post("/api/import", json=backup).json()["skipped"] == 1
    r = b.post("/api/import", json=backup)
    assert r.status_code == 200, r.text
    assert r.json()["added"] == 1
    assert b.post("/api/import", json=backup).json()["skipped"] == 1
    assert a.get("/api/export?format=csv").status_code == 200
    assert a.delete("/api/exams/" + eid).status_code == 200
    assert a.get("/api/exams/" + eid).status_code == 404
    assert a.post("/api/auth/logout").status_code == 200
    assert a.get("/api/exams").status_code == 401
    assert (
        a.post(
            "/api/auth/login",
            json={"email": "student-a", "password": "strong-test-password"},
        ).status_code
        == 200
    )
    assert (
        a.patch(
            "/api/auth/me",
            json={
                "old_password": "strong-test-password",
                "password": "new-strong-password",
                "username": "변경",
            },
        ).status_code
        == 200
    )
    a.post("/api/auth/logout")
    assert (
        a.post(
            "/api/auth/login",
            json={"email": "student-a", "password": "strong-test-password"},
        ).status_code
        == 401
    )
    assert (
        a.post(
            "/api/auth/login",
            json={"email": "student-a", "password": "new-strong-password"},
        ).status_code
        == 200
    )


def test_upload_to_engine_save_retrieve():
    a = TestClient(app)
    b = TestClient(app)
    register(a, "upload-a")
    register(b, "upload-b")
    image = ROOT / "output/test-fixtures/virtual-20260930.png"
    if not image.exists():
        from omr import OMREngine
        from tests.test_omr import marked
        from omr.io import write_image

        write_image(image, marked(OMREngine())[0])
    with image.open("rb") as f:
        r = a.post("/api/omr/analyze", files={"file": ("omr.png", f, "image/png")})
    assert r.status_code == 200, r.text
    result = r.json()
    page = result["pages"][0]
    assert page["date"] == "2026-0930"
    assert page["answers"]["16"]["answer"] == 128
    fid = page["files"]["aligned"]
    assert a.get("/api/files/" + fid).status_code == 200
    assert b.get("/api/files/" + fid).status_code == 404
    data = payload()
    data["file_ids"] = result["file_ids"]
    data["exam_date"] = page["date_details"]["iso"]
    for q in data["subjects"][0]["questions"]:
        recognition = page["answers"][str(q["number"])]
        q.update(
            user_answer=str(recognition["answer"]),
            confidence=recognition["confidence"],
            crop_file_id=recognition["crop_file_id"],
            recognition=recognition,
        )
    r = a.post("/api/exams", json=data)
    assert r.status_code == 200, r.text
    e = r.json()
    assert e["exam_date"] == "2026-09-30"
    assert e["subjects"][0]["questions"][15]["user_answer"] == "128"
    assert a.get("/api/wrong-answers").json()
    assert b.post("/api/exams", json=data).status_code == 422
    backup = a.get("/api/export").json()
    assert len(backup["files"]) == len(e["file_ids"])
    assert b.post("/api/import", json=backup).json()["added"] == 1
    restored = b.get("/api/exams").json()[0]
    restored_crop = restored["subjects"][0]["questions"][15]["crop_file_id"]
    assert (
        restored_crop
        and restored_crop != e["subjects"][0]["questions"][15]["crop_file_id"]
    )
    assert b.get("/api/files/" + restored_crop).status_code == 200
    assert a.get("/api/files/" + restored_crop).status_code == 404
    eid = e["id"]
    assert a.delete("/api/exams/" + eid).status_code == 200
    assert a.get("/api/files/" + fid).status_code == 404


def test_validation_partial_grading_and_csrf():
    a = TestClient(app)
    register(a, "validation")
    data = payload()
    data["subjects"][0]["questions"][0]["grading_status"] = None
    r = a.post("/api/exams", json=data)
    assert r.json()["subjects"][0]["auto_score"] is None
    data["subjects"][0]["questions"][0]["user_answer"] = "6"
    assert a.post("/api/exams", json=data).status_code == 422
    data = payload()
    data["subjects"].append(data["subjects"][0])
    assert a.post("/api/exams", json=data).status_code == 422
    assert (
        a.post(
            "/api/exams", json=payload(), headers={"Origin": "https://hostile.example"}
        ).status_code
        == 403
    )
    assert (
        a.post(
            "/api/omr/analyze", files={"file": ("bad.html", b"<html/>", "text/html")}
        ).status_code
        == 422
    )
