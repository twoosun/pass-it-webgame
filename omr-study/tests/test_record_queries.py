from fastapi.testclient import TestClient
from sqlalchemy import event
from tests.test_web import register, payload
from backend.main import app
from backend.database import engine


def test_archive_and_wrong_answers_use_bounded_queries():
    client = TestClient(app)
    register(client, "archive-query-count")
    for number in range(8):
        data = payload()
        data["name"] = f"Query test {number}"
        assert client.post("/api/exams", json=data).status_code == 200
    statements = []

    def capture(connection, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        response = client.get("/api/exams")
        assert response.status_code == 200
        assert len(response.json()) == 8
        assert len(statements) <= 7, len(statements)
        statements.clear()
        response = client.get("/api/wrong-answers")
        assert response.status_code == 200
        assert len(response.json()) == 8
        assert len(statements) <= 4, len(statements)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
