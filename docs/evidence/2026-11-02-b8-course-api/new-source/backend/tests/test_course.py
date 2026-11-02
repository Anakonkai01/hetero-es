"""The opt-in API-only course demo has independent identity and read-only student data."""

import json
import os
import time
import uuid

from fastapi.testclient import TestClient
import pytest

from backend.apps.factory import create_app
from backend.services.devices import AgentRuntime
from test_oidc import ISSUER, jwks_server, signed, keys as keys

PATHS = ("/hello", "/secure", "/student", "/students-db")


@pytest.mark.parametrize("role", ["all", "api", "devices", "storage", "scheduler"])
def test_course_routes_are_absent_by_default(tmp_path, monkeypatch, role):
    monkeypatch.delenv("HETEROES_COURSE_DEMO", raising=False)
    app = create_app(tmp_path / "default.sqlite", {}, AgentRuntime(), service=role, dispatch=False)
    with TestClient(app) as client:
        assert all(client.get(path).status_code == 404 for path in PATHS)


@pytest.mark.parametrize("role", ["all", "devices", "storage", "scheduler"])
def test_course_flag_does_not_register_routes_on_other_roles(tmp_path, monkeypatch, role):
    monkeypatch.setenv("HETEROES_COURSE_DEMO", "1")
    app = create_app(tmp_path / "other.sqlite", {}, AgentRuntime(), service=role, dispatch=False)
    with TestClient(app) as client:
        assert all(client.get(path).status_code == 404 for path in PATHS)


@pytest.fixture
def course(tmp_path, monkeypatch, keys):
    students = tmp_path / "students.json"
    rows = [{"id": 1, "name": "Course fixture", "major": "IT", "gpa": 3.5}]
    students.write_text(json.dumps(rows))
    monkeypatch.setenv("HETEROES_COURSE_DEMO", "1")
    monkeypatch.setenv("HETEROES_COURSE_STUDENTS_FILE", str(students))
    monkeypatch.setenv(
        "HETEROES_COURSE_STUDENTDB_URL", "postgresql+psycopg://course:never-publish-db-password@127.0.0.1:1/studentdb"
    )
    with jwks_server(keys) as server:
        monkeypatch.setenv("HETEROES_OIDC_ISSUER", ISSUER)
        monkeypatch.setenv("HETEROES_OIDC_JWKS_URL", server.url)
        app = create_app(tmp_path / "course.sqlite", {}, AgentRuntime(), service="api", dispatch=False)
        with TestClient(app) as client:
            yield client, app.state.store, students, rows


def test_hello_exact_response_and_mounted_json_is_read_fresh(course):
    client, _, path, rows = course
    assert client.get("/hello").json() == {"message": "Hello from App Server!"}
    assert client.get("/student").json() == rows
    rows.append({"id": 2, "name": "Updated fixture", "major": "AI", "gpa": 3.0})
    path.write_text(json.dumps(rows))
    assert client.get("/student").json() == rows


@pytest.mark.parametrize("kind", ["missing", "malformed", "oversized", "oversized-whitespace", "object"])
def test_mounted_json_errors_are_generic_and_bounded(course, capsys, kind):
    client, _, path, _ = course
    if kind == "missing":
        path.unlink()
    elif kind == "malformed":
        path.write_text("never-publish-json-error-marker")
    elif kind == "object":
        path.write_text('{"unexpected":"object"}')
    elif kind == "oversized-whitespace":
        # Keep the bounded prefix valid JSON so parsing cannot mask a missing size guard.
        path.write_text("[]" + " " * (2 * 1024 * 1024))
    else:
        path.write_text(json.dumps(["never-publish-json-error-marker" * 100000]))
    response = client.get("/student")
    assert response.status_code == 503
    assert response.json() == {"message": "Course student file is unavailable"}
    assert "never-publish" not in response.text + capsys.readouterr().out
    assert str(path) not in response.text


def test_secure_uses_flask_app_identity_without_registering_a_lab_account(course, keys):
    client, store, _, _ = course
    assert client.get("/secure").status_code == 401
    response = client.get("/secure", headers={"Authorization": "Bearer " + signed(keys[0], aud="flask-app")})
    assert response.status_code == 200
    assert response.json() == {"message": "Secure resource OK", "preferred_username": "researcher"}
    assert (
        client.get("/secure", headers={"Authorization": "Basic " + signed(keys[0], aud="flask-app")}).status_code == 401
    )
    response = client.get(
        "/secure", headers={"Authorization": "Bearer " + signed(keys[0], aud="account", azp="flask-app")}
    )
    assert response.status_code == 200
    with store.db() as db:
        assert db.execute("SELECT count(*) FROM users").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0


@pytest.mark.parametrize("kind", ["web-client", "expired", "wrong-signature", "wrong-issuer", "malformed"])
def test_secure_rejects_untrusted_or_other_client_tokens(course, keys, capsys, kind):
    client, _, _, _ = course
    changes = {"aud": "flask-app"}
    if kind == "web-client":
        changes["aud"] = "heteroes-web"
    elif kind == "expired":
        changes["exp"] = time.time() - 120
    elif kind == "wrong-issuer":
        changes["iss"] = ISSUER + "/wrong"
    token = (
        "never-publish-malformed-token" if kind == "malformed" else signed(keys[kind == "wrong-signature"], **changes)
    )
    response = client.get("/secure", headers={"Authorization": "Bearer " + token})
    assert response.status_code == 401
    assert token not in response.text + capsys.readouterr().out


def test_student_db_outage_does_not_expose_url_or_credentials(course, capsys):
    client, _, _, _ = course
    response = client.get("/students-db")
    assert response.status_code == 503
    assert response.json() == {"message": "Course student database is unavailable"}
    assert "never-publish" not in response.text + capsys.readouterr().out
    assert "postgresql" not in response.text


@pytest.mark.parametrize("url", ["sqlite:///students.sqlite", "never-publish-malformed-DSN", None])
def test_course_database_configuration_is_postgresql_only_with_safe_errors(url):
    from backend.services.course import CourseDemo

    with pytest.raises(ValueError) as error:
        CourseDemo(issuer=ISSUER, jwks_url="http://127.0.0.1:1/jwks", students_file="students.json", studentdb_url=url)
    assert str(error.value) == "Course demo requires a PostgreSQL student database URL"


if os.environ.get("HETEROES_TEST_DATABASE_URL"):

    def test_student_db_is_separate_and_uses_an_actual_read_only_role(
        course, fresh_postgres_database, monkeypatch, tmp_path
    ):
        from sqlalchemy import create_engine, text
        from sqlalchemy.exc import DBAPIError

        client, _, _, _ = course
        target = fresh_postgres_database()
        admin = create_engine(target)
        role = "course_reader_" + uuid.uuid4().hex
        reader = None
        try:
            with admin.begin() as db:
                db.execute(text("CREATE ROLE " + role + " NOLOGIN"))
                db.execute(
                    text(
                        "CREATE TABLE students(id INTEGER PRIMARY KEY,student_id TEXT,fullname TEXT,dob DATE,major TEXT)"
                    )
                )
                db.execute(
                    text(
                        "INSERT INTO students VALUES (2,'fixture02','Student two','2002-02-02','AI'),(1,'fixture01','Student one','2001-01-01','IT'),(3,'fixture03','Student three',NULL,'IT')"
                    )
                )
                db.execute(text("GRANT USAGE ON SCHEMA public TO " + role))
                db.execute(text("GRANT SELECT ON students TO " + role))
            read_url = target.set(query={"options": "-crole=" + role})
            monkeypatch.setenv("HETEROES_COURSE_STUDENTDB_URL", read_url.render_as_string(hide_password=False))
            app = create_app(tmp_path / "separate.sqlite", {}, AgentRuntime(), service="api", dispatch=False)
            with TestClient(app) as separate_client:
                response = separate_client.get("/students-db")
            assert response.status_code == 200
            rows = response.json()
            assert [r["id"] for r in rows] == [1, 2, 3]
            assert rows[0] == {
                "id": 1,
                "student_id": "fixture01",
                "fullname": "Student one",
                "dob": "2001-01-01",
                "major": "IT",
            }
            assert rows[2]["dob"] is None
            reader = create_engine(read_url)
            with reader.connect() as db:
                assert db.execute(text("SELECT current_user")).scalar_one() == role
                assert db.execute(text("SELECT has_table_privilege(current_user,'students','SELECT')")).scalar_one()
                assert not db.execute(text("SELECT has_table_privilege(current_user,'students','INSERT')")).scalar_one()
                with pytest.raises(DBAPIError):
                    db.execute(text("INSERT INTO students(id) VALUES (4)"))
            with admin.connect() as db:
                assert db.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
                ).scalars().all() == ["students"]
        finally:
            if reader is not None:
                reader.dispose()
            with admin.begin() as db:
                db.execute(text("DROP OWNED BY " + role))
                db.execute(text("DROP ROLE " + role))
            admin.dispose()
