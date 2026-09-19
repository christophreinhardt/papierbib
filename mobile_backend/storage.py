"""One SQLite transaction owns original, crop and metadata; no loose image files."""
import hashlib
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager, closing
from datetime import datetime, timezone
from uuid import uuid4

def now():
    return datetime.now(timezone.utc).isoformat()

class Store:
    def __init__(self, path):
        self.path = path

    @contextmanager
    def connect(self):
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA foreign_keys=ON')
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                raise RuntimeError('Unbekannte Datenbankversion; Dienst nicht gestartet.')
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript("""
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY, name TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS captures (
                    photo_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects,
                    capture_type TEXT NOT NULL, original BLOB NOT NULL, mime TEXT NOT NULL,
                    sha256 TEXT NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
                    created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS crops (
                    crop_id TEXT PRIMARY KEY, photo_id TEXT NOT NULL REFERENCES captures,
                    transform TEXT NOT NULL, image BLOB NOT NULL,
                    width INTEGER NOT NULL, height INTEGER NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS book_records (
                    book_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects,
                    photo_id TEXT REFERENCES captures, crop_id TEXT REFERENCES crops,
                    status TEXT NOT NULL DEFAULT 'needs_scan',
                    metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (
                    digest TEXT PRIMARY KEY, expires REAL NOT NULL, credential TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS rate_limits (
                    bucket TEXT PRIMARY KEY, start REAL NOT NULL, hits INTEGER NOT NULL);
                PRAGMA user_version=1;
            """)

    def throttle(self, bucket, maximum, seconds):
        stamp = time.time()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM rate_limits WHERE start < ?', (stamp - 3600,))
            row = db.execute('SELECT * FROM rate_limits WHERE bucket=?', (bucket,)).fetchone()
            if row and stamp - row['start'] < seconds:
                if row['hits'] >= maximum:
                    return False
                db.execute('UPDATE rate_limits SET hits=hits+1 WHERE bucket=?', (bucket,))
            else:
                db.execute('INSERT OR REPLACE INTO rate_limits VALUES (?,?,1)', (bucket, stamp))
        return True

    def new_session(self, credential, duration):
        token = secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute('DELETE FROM sessions WHERE expires < ?', (time.time(),))
            db.execute('INSERT INTO sessions VALUES (?,?,?)',
                       (self.digest(token), time.time() + duration, credential))
        return token

    @staticmethod
    def digest(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def authenticated(self, token, credential):
        if not token or len(token) > 128:
            return False
        with self.connect() as db:
            return db.execute('SELECT 1 FROM sessions WHERE digest=? AND expires>? AND credential=?',
                              (self.digest(token), time.time(), credential)).fetchone() is not None

    def logout(self, token):
        with self.connect() as db:
            db.execute('DELETE FROM sessions WHERE digest=?', (self.digest(token),))

    def projects(self):
        with self.connect() as db:
            return [dict(x) for x in db.execute('SELECT * FROM projects ORDER BY updated_at DESC')]

    def create_project(self, name):
        project = dict(project_id=str(uuid4()), name=name, created_at=now(), updated_at=now())
        with self.connect() as db:
            db.execute('INSERT INTO projects VALUES (:project_id,:name,:created_at,:updated_at)', project)
        return project

    def has_project(self, project_id):
        with self.connect() as db:
            return db.execute('SELECT 1 FROM projects WHERE project_id=?', (project_id,)).fetchone() is not None

    def save_capture(self, project_id, kind, original, image_info, crop, transform):
        photo_id, crop_id = str(uuid4()), str(uuid4())
        stamp = now()
        with self.connect() as db:
            db.execute('INSERT INTO captures VALUES (?,?,?,?,?,?,?,?,?)',
                       (photo_id, project_id, kind, original, image_info['mime'],
                        hashlib.sha256(original).hexdigest(), image_info['width'], image_info['height'], stamp))
            self._insert_crop(db, crop_id, photo_id, crop, transform, stamp)
            db.execute('UPDATE projects SET updated_at=? WHERE project_id=?', (stamp, project_id))
        return dict(photo_id=photo_id, crop_id=crop_id)

    def _insert_crop(self, db, crop_id, photo_id, crop, transform, stamp):
        db.execute('INSERT INTO crops VALUES (?,?,?,?,?,?,?)',
                   (crop_id, photo_id, json.dumps(transform), crop['data'], crop['width'], crop['height'], stamp))

    def save_crop(self, photo_id, crop, transform):
        crop_id, stamp = str(uuid4()), now()
        with self.connect() as db:
            self._insert_crop(db, crop_id, photo_id, crop, transform, stamp)
            db.execute('UPDATE projects SET updated_at=? WHERE project_id=(SELECT project_id FROM captures WHERE photo_id=?)',
                       (stamp, photo_id))
        return dict(photo_id=photo_id, crop_id=crop_id)

    def captures(self, project_id):
        with self.connect() as db:
            captures = [dict(x) for x in db.execute(
                'SELECT photo_id,capture_type,width,height,created_at FROM captures WHERE project_id=? ORDER BY created_at DESC',
                (project_id,))]
            for item in captures:
                item['crops'] = [dict(x) for x in db.execute(
                    'SELECT crop_id,transform,width,height,created_at FROM crops WHERE photo_id=? ORDER BY created_at DESC',
                    (item['photo_id'],))]
                for crop in item['crops']:
                    crop['transform'] = json.loads(crop['transform'])
            return captures

    def original(self, photo_id):
        with self.connect() as db:
            row = db.execute('SELECT original,mime FROM captures WHERE photo_id=?', (photo_id,)).fetchone()
            return (bytes(row['original']), row['mime']) if row else None

    def crop(self, crop_id):
        with self.connect() as db:
            row = db.execute('SELECT image FROM crops WHERE crop_id=?', (crop_id,)).fetchone()
            return bytes(row[0]) if row else None
