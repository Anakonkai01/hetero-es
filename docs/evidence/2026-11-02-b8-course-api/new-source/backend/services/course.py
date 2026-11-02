"""Opt-in course demonstrations share the OIDC verifier, but never create lab accounts."""

import json
from pathlib import Path

from ..core.errors import ServiceError
from ..repositories.course import CourseStudentsRepository
from .oidc import OIDCVerifier

_MAX_STUDENTS_BYTES = 1024 * 1024


class CourseDemo:
    def __init__(self, *, issuer, jwks_url, students_file, studentdb_url):
        from sqlalchemy.engine import make_url
        from sqlalchemy.exc import ArgumentError

        self.verifier = OIDCVerifier(issuer, jwks_url, client_id="flask-app")
        if not isinstance(students_file, str) or not students_file:
            raise ValueError("Course demo requires a mounted students JSON file")
        self.students_file = Path(students_file)
        try:
            url = make_url(studentdb_url)
            if url.drivername not in {"postgres", "postgresql", "postgresql+psycopg"} or not url.database:
                raise ValueError
            self.studentdb_url = url.set(drivername="postgresql+psycopg")
        except (ArgumentError, TypeError, ValueError):
            raise ValueError("Course demo requires a PostgreSQL student database URL") from None

    def secure(self, authorization):
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise ServiceError(401, "Bearer identity token required", headers={"WWW-Authenticate": "Bearer"})
        claims = self.verifier.verify(token)
        return {"message": "Secure resource OK", "preferred_username": claims["preferred_username"]}

    def students(self):
        try:
            with self.students_file.open("rb") as stream:
                payload = stream.read(_MAX_STUDENTS_BYTES + 1)
            if len(payload) > _MAX_STUDENTS_BYTES:
                raise ValueError
            rows = json.loads(payload)
            if not isinstance(rows, list):
                raise ValueError
            return rows
        except (OSError, ValueError):
            raise ServiceError(503, "Course student file is unavailable") from None

    def students_db(self):
        try:
            return CourseStudentsRepository.read(self.studentdb_url)
        except Exception:
            raise ServiceError(503, "Course student database is unavailable") from None
