"""Versioned local persistence. Connections are short-lived and never shared across threads."""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def now():
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path=None):
        self.path = str(path or os.environ.get('INTELLIGENCE_DB_PATH', ROOT / 'data' / 'intelligence.sqlite3'))
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)')
            for file in sorted((ROOT / 'migrations').glob('*.sql')):
                version = int(file.name.split('_')[0])
                if db.execute('SELECT 1 FROM schema_migrations WHERE version=?', (version,)).fetchone():
                    continue
                # executescript handles its own transaction; migration+version are atomic.
                stamp = now()
                db.executescript('BEGIN IMMEDIATE;\n' + file.read_text() + f"\nINSERT INTO schema_migrations VALUES ({version},'{stamp}');\nCOMMIT;")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def rows(self, sql, params=()):
        with self.connect() as db:
            return [dict(row) for row in db.execute(sql, params)]
