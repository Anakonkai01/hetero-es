"""The course database is independent of product schema initialization and write locks."""


class CourseStudentsRepository:
    @staticmethod
    def read(url):
        from sqlalchemy import create_engine, text
        from sqlalchemy.pool import NullPool

        engine = create_engine(url, poolclass=NullPool, hide_parameters=True, connect_args={"connect_timeout": 5})
        try:
            with engine.begin() as db:
                db.execute(text("SET TRANSACTION READ ONLY"))
                rows = db.execute(text("SELECT id,student_id,fullname,dob,major FROM students ORDER BY id")).mappings()
                return [dict(row) for row in rows]
        finally:
            engine.dispose()
