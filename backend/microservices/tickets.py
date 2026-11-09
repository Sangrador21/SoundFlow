"""Persistencia privada del servicio de reproducción. Ningún otro servicio abre esta BD."""
import json
from pathlib import Path
import sqlite3
import threading
import time
import uuid


class TicketStore:
    def __init__(self, path):
        if str(path) != ':memory:':
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('''CREATE TABLE IF NOT EXISTS tickets (
            seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
            song_id TEXT NOT NULL, start REAL NOT NULL, created REAL NOT NULL,
            state TEXT NOT NULL, stream TEXT, reason TEXT NOT NULL,
            error_code INTEGER NOT NULL DEFAULT 0, trace TEXT NOT NULL)''')
        self.db.commit()

    def create(self, song, start, trace):
        ticket_id = uuid.uuid4().hex
        with self.lock, self.db:
            self.db.execute('''INSERT INTO tickets
                (id,song_id,start,created,state,reason,trace) VALUES (?,?,?,?,?,?,?)''',
                (ticket_id, song, start, time.time(), 'waiting', 'Buscando un servidor disponible.', trace))
        return ticket_id

    def get(self, ticket_id):
        with self.lock:
            row = self.db.execute('SELECT * FROM tickets WHERE id=?', (ticket_id,)).fetchone()
            if row is None:
                return None
            result = dict(row)
            result['stream'] = json.loads(result['stream']) if result['stream'] else None
            return result

    def head(self):
        with self.lock:
            row = self.db.execute("SELECT id FROM tickets WHERE state='waiting' ORDER BY seq LIMIT 1").fetchone()
            return self.get(row['id']) if row else None

    def change(self, ticket_id, state, reason, code=0, stream=None, *, expected='waiting'):
        with self.lock, self.db:
            cursor = self.db.execute('''UPDATE tickets SET state=?,reason=?,error_code=?,stream=?
                WHERE id=? AND state=?''', (state, reason, code,
                json.dumps(stream) if stream else None, ticket_id, expected))
            return bool(cursor.rowcount)

    def position(self, ticket):
        if ticket['state'] != 'waiting':
            return 0
        with self.lock:
            return self.db.execute("SELECT COUNT(*) FROM tickets WHERE state='waiting' AND seq<=?",
                                   (ticket['seq'],)).fetchone()[0]

    def expire(self, timeout):
        with self.lock, self.db:
            self.db.execute("""UPDATE tickets SET state='failed',error_code=504,
                reason='Se agotó el tiempo de espera. Puedes volver a intentar.'
                WHERE state='waiting' AND created<?""", (time.time() - timeout,))
            self.db.execute("DELETE FROM tickets WHERE state!='waiting' AND created<?", (time.time() - 3600,))

    def close(self):
        with self.lock:
            self.db.close()
