"""Thin API adapters for the separately enabled course exercises."""

from fastapi import Request


def install_routes(app, course):
    @app.get("/hello")
    def hello():
        return {"message": "Hello from App Server!"}

    @app.get("/secure")
    def secure(request: Request):
        return course.secure(request.headers.get("authorization"))

    @app.get("/student")
    def student():
        return course.students()

    @app.get("/students-db")
    def students_db():
        return course.students_db()
