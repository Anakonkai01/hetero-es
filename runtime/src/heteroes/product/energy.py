"""Persistent, component-scoped energy accounting; no invented wall power."""
from datetime import datetime, timedelta
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
import time


class EnergyLedger:
    def __init__(self, directory):
        self.root = Path(directory)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.root / 'energy.sqlite'
        self.session = {}
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS meters(id TEXT PRIMARY KEY,boot TEXT,tick REAL,at REAL,value REAL,kind TEXT);
                CREATE TABLE IF NOT EXISTS totals(id TEXT PRIMARY KEY,wh REAL NOT NULL,seconds REAL NOT NULL,since REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS days(id TEXT,day TEXT,wh REAL NOT NULL,seconds REAL NOT NULL,PRIMARY KEY(id,day));
            ''')
        os.chmod(self.path, 0o600)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.execute('PRAGMA journal_mode=WAL')
        try:
            with db:
                yield db
        finally:
            db.close()

    def record(self, identity, boot, tick, at, value, kind='watts', counter_range=None):
        """Deduplicate overlapping agents; discard downtime and counter resets."""
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            previous = db.execute('SELECT boot,tick,at,value,kind FROM meters WHERE id=?', (identity,)).fetchone()
            total = db.execute('SELECT wh,seconds FROM totals WHERE id=?', (identity,)).fetchone()
            self.session.setdefault(identity, total or (0, 0))
            if previous and previous[0] == boot and tick <= previous[1]:
                return self.summary(identity, at, db)
            db.execute('INSERT OR IGNORE INTO totals VALUES (?,0,0,?)', (identity, at))
            if value is not None and previous and previous[0] == boot and previous[4] == kind:
                dt = tick - previous[1]
                if 0 < dt <= 30 and 0 < at - previous[2] <= 31:
                    if kind == 'counter':
                        delta = value - previous[3]
                        if delta < 0 and counter_range and previous[3] > counter_range * .75 and value < counter_range * .25:
                            delta += counter_range
                        wh = delta / 3_600_000_000 if delta >= 0 else None
                    else:
                        wh = (value + previous[3]) * .5 * dt / 3600
                    if wh is not None and 0 <= wh <= 100_000 * dt / 3600:
                        db.execute('UPDATE totals SET wh=wh+?,seconds=seconds+? WHERE id=?', (wh, dt, identity))
                        # Split short observed intervals at local calendar midnight.
                        start, end = previous[2], at
                        while start < end:
                            local = datetime.fromtimestamp(start).astimezone()
                            next_date = local.date() + timedelta(days=1)
                            midnight = datetime.combine(next_date, datetime.min.time()).astimezone().timestamp()
                            boundary = min(end, midnight)
                            fraction = (boundary - start) / max(.000001, end - previous[2])
                            db.execute('INSERT INTO days VALUES (?,?,?,?) ON CONFLICT(id,day) DO UPDATE SET wh=wh+excluded.wh,seconds=seconds+excluded.seconds',
                                       (identity, local.date().isoformat(), wh * fraction, dt * fraction))
                            start = boundary
            if value is None:
                db.execute('DELETE FROM meters WHERE id=?', (identity,))
            else:
                db.execute('INSERT OR REPLACE INTO meters VALUES (?,?,?,?,?,?)', (identity, boot, tick, at, value, kind))
            return self.summary(identity, at, db)

    def summary(self, identity, at=None, db=None):
        if db is None:
            with self.db() as connection:
                return self.summary(identity, at, connection)
        day = datetime.fromtimestamp(at if at is not None else time.time()).astimezone().date().isoformat()
        total = db.execute('SELECT wh,seconds,since FROM totals WHERE id=?', (identity,)).fetchone() or (0, 0, None)
        daily = db.execute('SELECT wh,seconds FROM days WHERE id=? AND day=?', (identity, day)).fetchone() or (0, 0)
        monthly = db.execute('SELECT coalesce(sum(wh),0),coalesce(sum(seconds),0) FROM days WHERE id=? AND day LIKE ?', (identity, day[:7] + '%')).fetchone()
        baseline = self.session.get(identity, total[:2])
        return {'sessionWh': max(0, total[0] - baseline[0]), 'sessionSampledSeconds': max(0, total[1] - baseline[1]),
                'todayWh': daily[0], 'monthWh': monthly[0], 'lifetimeWh': total[0],
                'sampledSeconds': total[1], 'todaySampledSeconds': daily[1], 'monthSampledSeconds': monthly[1],
                'since': total[2], 'day': day, 'month': day[:7],
                'timezone': str(datetime.now().astimezone().tzinfo)}

    def break_missing(self, prefix, active):
        """A known missing hardware reading must break even a short interval."""
        with self.db() as db:
            rows = db.execute('SELECT id FROM meters WHERE id LIKE ?', (prefix + '%',)).fetchall()
            for (identity,) in rows:
                if identity not in active:
                    db.execute('DELETE FROM meters WHERE id=?', (identity,))
