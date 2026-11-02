"""Read-only product observations. No raw identifiers, SQL parameters or body strings are metric labels."""


class ObservabilityRepository:
    @staticmethod
    def snapshot(db):
        return {
            "devices": db.execute("SELECT id,status,seen,telemetry FROM devices").fetchall(),
            "experiments": db.execute("SELECT body,snapshot FROM experiments").fetchall(),
            "queue": db.execute("SELECT count(*) FROM queue").fetchone()[0],
            "storage": db.execute("""
                SELECT CAST(coalesce(sum(CASE WHEN status='READY' THEN size ELSE 0 END),0) AS BIGINT),
                       CAST(coalesce(sum(CASE WHEN status<>'READY' THEN size ELSE 0 END),0) AS BIGINT)
                FROM cloud_objects
            """).fetchone(),
        }
