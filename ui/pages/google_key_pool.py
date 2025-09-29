# google_key_pool.py
# v1.1 — KeyPool для Google JSON-ключів (OAuth Desktop / API key / Service Account)
# Залежності: стандартна бібліотека Python + requests
# УВАГА: "шифрування" нижче лише для ТЕСТУ (Base64+XOR). Для продакшну підключіть KMS/AES-256.

from __future__ import annotations
import os, json, time, base64, sqlite3, threading, hashlib
from typing import Optional, Tuple, List, Callable
import requests

DB_PATH = os.path.join(os.getcwd(), "keypool.db")

STATUS_VALID = "VALID"
STATUS_INVALID = "INVALID"
STATUS_QUOTA = "QUOTA_EXCEEDED"
STATUS_LOCKED = "TEMP_LOCKED"

def utc() -> int: return int(time.time())

# ---------- тимчасове «шифрування» для тесту ----------
def _kdf(secret: str) -> bytes:
    return hashlib.sha256(("demo:"+secret).encode("utf-8")).digest()

def _enc(secret: str, data: bytes) -> str:
    key = _kdf(secret)
    xored = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return base64.urlsafe_b64encode(xored).decode("ascii")

def _dec(secret: str, token: str) -> bytes:
    key = _kdf(secret)
    raw = base64.urlsafe_b64decode(token.encode("ascii"))
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(raw))

def _derive_id(obj: dict, raw: bytes) -> tuple[str, str]:
    """
    Повертає (kid, kind):
      kind ∈ {"oauth","apikey","service","raw"}
    """
    # OAuth Desktop / Web
    client_id = (obj.get("installed") or {}).get("client_id") or (obj.get("web") or {}).get("client_id")
    if client_id:
        return f"oauth:{client_id}", "oauth"
    # API key
    api_key = obj.get("api_key") or obj.get("API_KEY") or obj.get("key")
    if api_key:
        return f"apikey:{api_key}", "apikey"
    # Service Account
    if obj.get("private_key_id") or obj.get("client_email"):
        pid = obj.get("private_key_id") or obj.get("client_email")
        return f"service:{pid}", "service"
    # Фолбек — хеш умісту
    return f"raw:{hashlib.sha1(raw).hexdigest()[:12]}", "raw"

class KeyMeta:
    def __init__(self, kid: str, status: str, added_at: int, last_check: int, quota_reset_at: int, errors: int):
        self.id = kid
        self.status = status
        self.added_at = added_at
        self.last_check = last_check
        self.quota_reset_at = quota_reset_at
        self.errors = errors

class KeyPool:
    """
    - SQLite сховище з зашифрованим JSON ключем
    - ДЕДУПЛІКАЦІЯ: за client_id (OAuth), за api_key (API key), за client_email/private_key_id (Service)
    - авто-ротація при quotaExceeded / rateLimitExceeded (для API key запитів)
    - щогодинний health-check
    - ручне перемикання
    - колбек-нотифікації
    """

    def __init__(self, admin_secret: str, notifier: Optional[Callable[[str], None]] = None):
        self.admin_secret = admin_secret or "demo"
        self.notifier = notifier or (lambda msg: None)
        self._lock = threading.RLock()
        self._ensure_db()
        self._cur_id: Optional[str] = None
        self._stop = False
        self._hc_thread = threading.Thread(target=self._health_loop, daemon=True)
        self._hc_thread.start()

    # ----- DB -----
    def _conn(self): return sqlite3.connect(DB_PATH)

    def _ensure_db(self):
        con = self._conn(); cur = con.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS keys(
            id TEXT PRIMARY KEY,
            enc_json TEXT NOT NULL,
            status TEXT NOT NULL,
            added_at INTEGER NOT NULL,
            last_check INTEGER NOT NULL,
            quota_reset_at INTEGER NOT NULL,
            errors INTEGER NOT NULL
        )""")
        con.commit(); con.close()

    # ----- CRUD -----
    def add_key_from_file(self, path: str) -> str:
        with open(path, "rb") as f:
            raw = f.read()
        return self.add_key_from_bytes(raw)

    def add_key_from_bytes(self, raw: bytes) -> str:
        try:
            obj = json.loads(raw.decode("utf-8"))
        except Exception:
            raise ValueError("Файл не схожий на валідний JSON ключ")

        kid, kind = _derive_id(obj, raw)

        # ДЕДУПЛІКАЦІЯ
        con = self._conn(); cur = con.cursor()
        cur.execute("SELECT 1 FROM keys WHERE id=?", (kid,))
        if cur.fetchone() is not None:
            con.close()
            raise ValueError(f"Ключ уже існує (дублікат): {kid}")

        enc = _enc(self.admin_secret, raw)
        now = utc()
        # OAuth-клієнт не має прямого API-пінгу — позначаємо VALID; health-check пропустить
        status = STATUS_VALID if kind in ("oauth", "service", "raw") else STATUS_VALID
        cur.execute("""INSERT INTO keys(id, enc_json, status, added_at, last_check, quota_reset_at, errors)
                       VALUES(?,?,?,?,?,?,?)""",
                    (kid, enc, status, now, 0, 0, 0))
        con.commit(); con.close()
        return kid

    def delete_key(self, kid: str) -> None:
        con = self._conn(); cur = con.cursor()
        cur.execute("DELETE FROM keys WHERE id=?", (kid,))
        con.commit(); con.close()
        if self._cur_id == kid: self._cur_id = None

    def list_keys(self) -> List[KeyMeta]:
        con = self._conn(); cur = con.cursor()
        cur.execute("SELECT id,status,added_at,last_check,quota_reset_at,errors FROM keys")
        rows = [KeyMeta(*r) for r in cur.fetchall()]
        con.close()
        return rows

    def get_valid_counts(self) -> Tuple[int, int]:
        con = self._conn(); cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM keys")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM keys WHERE status=?", (STATUS_VALID,))
        valid = cur.fetchone()[0]
        con.close()
        return valid, total

    def _load_json(self, kid: str) -> dict:
        con = self._conn(); cur = con.cursor()
        cur.execute("SELECT enc_json FROM keys WHERE id=?", (kid,))
        r = cur.fetchone()
        con.close()
        if not r: raise KeyError("Key not found")
        raw = _dec(self.admin_secret, r[0])
        return json.loads(raw.decode("utf-8"))

    # ----- вибір ключа -----
    def current_key_id(self) -> Optional[str]:
        with self._lock:
            if self._cur_id and self._get_status(self._cur_id) == STATUS_VALID:
                return self._cur_id
            con = self._conn(); cur = con.cursor()
            cur.execute("SELECT id FROM keys WHERE status=? ORDER BY added_at ASC", (STATUS_VALID,))
            r = cur.fetchone()
            con.close()
            self._cur_id = r[0] if r else None
            return self._cur_id

    def get_key_json(self) -> Optional[dict]:
        kid = self.current_key_id()
        return self._load_json(kid) if kid else None

    def manual_switch(self, kid: str) -> bool:
        with self._lock:
            st = self._get_status(kid)
            if st != STATUS_VALID: return False
            self._cur_id = kid
            return True

    def _get_status(self, kid: str) -> str:
        con = self._conn(); cur = con.cursor()
        cur.execute("SELECT status FROM keys WHERE id=?", (kid,))
        r = cur.fetchone(); con.close()
        return r[0] if r else STATUS_INVALID

    def _set_status(self, kid: str, status: str, *, inc_error=False):
        con = self._conn(); cur = con.cursor()
        if inc_error:
            cur.execute("UPDATE keys SET status=?, errors=errors+1, last_check=? WHERE id=?", (status, utc(), kid))
        else:
            cur.execute("UPDATE keys SET status=?, last_check=? WHERE id=?", (status, utc(), kid))
        con.commit(); con.close()

    def mark_quota(self, kid: str, reset_at: Optional[int] = None):
        con = self._conn(); cur = con.cursor()
        cur.execute("UPDATE keys SET status=?, quota_reset_at=?, last_check=?, errors=errors+1 WHERE id=?",
                    (STATUS_QUOTA, int(reset_at or 0), utc(), kid))
        con.commit(); con.close()
        self.notifier(f"[KeyPool] {kid} → QUOTA_EXCEEDED")

    def temp_lock(self, kid: str, minutes: int = 10):
        con = self._conn(); cur = con.cursor()
        cur.execute("UPDATE keys SET status=?, quota_reset_at=?, last_check=?, errors=errors+1 WHERE id=?",
                    (STATUS_LOCKED, utc() + minutes*60, utc(), kid))
        con.commit(); con.close()
        self.notifier(f"[KeyPool] {kid} → TEMP_LOCKED for {minutes}m")

    def mark_invalid(self, kid: str):
        self._set_status(kid, STATUS_INVALID, inc_error=True)
        self.notifier(f"[KeyPool] {kid} → INVALID")

    def mark_valid(self, kid: str):
        self._set_status(kid, STATUS_VALID)

    # ----- health-check -----
    def _health_loop(self):
        while not self._stop:
            try:
                self.health_check_all()
            except Exception as e:
                self.notifier(f"[KeyPool] health loop error: {e}")
            for _ in range(60):
                if self._stop: break
                time.sleep(60)

    def stop(self):
        self._stop = True

    def _probe(self, key_obj: dict):
        # OAuth Desktop/Web — не має api_key → вважаємо VALІD (перевірка робиться під час фактичного OAuth-флоу)
        if (key_obj.get("installed") or {}).get("client_id") or (key_obj.get("web") or {}).get("client_id"):
            return True, None
        # Service Account не підходить для YouTube Data (mine=true) — маркуємо INVALID
        if key_obj.get("private_key_id") or key_obj.get("client_email"):
            return False, "service_account_unsupported"
        # API key — робимо легкий пінг
        api_key = key_obj.get("api_key") or key_obj.get("API_KEY") or key_obj.get("key")
        if not api_key:
            return False, "no_api_key_field"
        url = "https://www.googleapis.com/youtube/v3/videos"
        params = {"part": "snippet", "id": "dQw4w9WgXcQ", "key": api_key}
        r = requests.get(url, params=params, timeout=12)
        if r.status_code == 200:
            return True, None
        try:
            data = r.json()
        except Exception:
            data = {}
        reason = (data.get("error", {}).get("errors") or [{}])[0].get("reason")
        if reason in ("quotaExceeded", "rateLimitExceeded"):
            return False, reason
        return False, reason or f"http_{r.status_code}"

    def health_check_all(self):
        rows = self.list_keys()
        for m in rows:
            try:
                obj = self._load_json(m.id)
            except Exception:
                self.mark_invalid(m.id); continue
            ok, reason = self._probe(obj)
            if ok:
                self.mark_valid(m.id)
            else:
                if reason in ("quotaExceeded", "rateLimitExceeded"):
                    self.mark_quota(m.id)
                elif reason == "service_account_unsupported":
                    self.mark_invalid(m.id)
                else:
                    self.mark_invalid(m.id)
        v, t = self.get_valid_counts()
        if v <= 2:
            self.notifier(f"[KeyPool] LOW KEYS: {v}/{t}")

    # ----- відправка запиту з авто-ротацією (для API-key запитів) -----
    def send_with_rotation(self, url: str, params: dict, *, method: str = "GET", headers: Optional[dict] = None, json_body=None) -> requests.Response:
        attempt = 0
        last_reason = None
        while True:
            attempt += 1
            kid = self.current_key_id()
            if not kid:
                raise RuntimeError("Немає жодного VALID ключа")
            kobj = self._load_json(kid)
            api_key = kobj.get("api_key") or kobj.get("API_KEY") or kobj.get("key")
            p = dict(params or {})
            if api_key:
                p["key"] = api_key
            session = requests
            try:
                if method == "GET":
                    r = session.get(url, params=p, headers=headers, timeout=20)
                else:
                    r = session.post(url, params=p, headers=headers, json=json_body, timeout=25)
            except Exception as e:
                self.temp_lock(kid, minutes=3)
                last_reason = str(e)
                continue

            if r.status_code == 200:
                return r

            reason = None
            try:
                data = r.json()
                reason = (data.get("error", {}).get("errors") or [{}])[0].get("reason")
            except Exception:
                pass

            if reason in ("quotaExceeded", "rateLimitExceeded"):
                self.mark_quota(kid)
                if attempt <= 6:
                    continue
            elif r.status_code in (400, 401, 403):
                self.mark_invalid(kid)
                if attempt <= 6:
                    continue
            else:
                self.temp_lock(kid, minutes=2)
                if attempt <= 4:
                    continue

            if reason: last_reason = reason
            r.raise_for_status()

def valid_indicator_text(pool: KeyPool) -> str:
    v, t = pool.get_valid_counts()
    return f"{v}/{t}"
