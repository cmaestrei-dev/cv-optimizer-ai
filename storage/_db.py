import json
import logging
import os
import re
import sqlite3

import config

logger = logging.getLogger(__name__)
_inited = False

_TURSO_URL = os.getenv("TURSO_DB_URL", "")
_TURSO_TOKEN = os.getenv("TURSO_AUTH_TOKEN", "")


def _is_turso() -> bool:
    return bool(_TURSO_URL and _TURSO_TOKEN)


def get_storage_info() -> dict:
    info = {"mode": "turso" if _is_turso() else "local", "connected": False}
    if _is_turso():
        try:
            result = _turso_execute("SELECT 1")
            info["connected"] = bool(result)
        except Exception:
            info["connected"] = False
    else:
        info["connected"] = True
    return info


def _get_db_path() -> str:
    return os.path.join(config.DATA_DIR, "cv_optimizer.db")


def _get_connection() -> sqlite3.Connection:
    os.makedirs(config.DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(_get_db_path())
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


# ── Turso HTTP wrapper ─────────────────────────────────────────────


def _turso_execute(sql: str, params: tuple = ()) -> list[dict]:
    import requests

    turso_url = _TURSO_URL.replace("libsql://", "https://")
    body = {
        "requests": [
            {
                "type": "execute",
                "stmt": {"sql": sql, "args": list(params) if params else []},
            }
        ]
    }
    resp = requests.post(
        f"{turso_url}/v2/pipeline",
        headers={
            "Authorization": f"Bearer {_TURSO_TOKEN}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results", [])
    if not results:
        raise RuntimeError(f"Turso returned empty results: {data}")
    result = results[0]
    if result.get("type") == "error":
        raise RuntimeError(f"Turso error: {result.get('error', result)}")
    inner = result.get("response", {}).get("result", {})
    cols = [c["name"] for c in inner.get("cols", [])]
    rows = inner.get("rows", [])
    parsed = []
    for row in rows:
        parsed.append({cols[i]: _turso_extract_value(v) for i, v in enumerate(row)})
    return parsed


def _turso_extract_value(val: dict | list | str | int | None) -> str | int | None:
    if isinstance(val, dict) and "value" in val:
        return val["value"]
    return val


def _turso_execute_script(sql: str) -> None:
    for statement in sql.split(";"):
        statement = statement.strip()
        if statement:
            _turso_execute(statement + ";")


# ── unified execute ────────────────────────────────────────────────


def _execute(sql: str, params: tuple = ()) -> list[dict]:
    if _is_turso():
        return _turso_execute(sql, params)

    conn = _get_connection()
    cursor = conn.execute(sql, params)
    rows = cursor.fetchall()
    result = [dict(r) for r in rows]
    conn.commit()
    conn.close()
    return result


def _execute_script(sql: str) -> None:
    if _is_turso():
        _turso_execute_script(sql)
        return

    conn = _get_connection()
    conn.executescript(sql)
    conn.commit()
    conn.close()


def _execute_one(sql: str, params: tuple = ()) -> dict | None:
    rows = _execute(sql, params)
    return rows[0] if rows else None


# ── init ───────────────────────────────────────────────────────────


def init_db() -> None:
    global _inited
    if _inited:
        return
    if not _is_turso():
        os.makedirs(config.DATA_DIR, exist_ok=True)
    _execute_script("""
        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            full_name TEXT DEFAULT '',
            email TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            linkedin_url TEXT DEFAULT '',
            github_url TEXT DEFAULT '',
            password_hash TEXT DEFAULT '',
            salt TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS experiences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
            content TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_experiences_user ON experiences(user_id);

        CREATE TABLE IF NOT EXISTS skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            category TEXT DEFAULT 'Otros',
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_skills_user ON skills(user_id);

        CREATE TABLE IF NOT EXISTS education_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
            content TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_education_user ON education_entries(user_id);
    """)
    _inited = True


def _migrate_all_legacy_profiles() -> None:
    if _is_turso():
        return
    if not os.path.isdir(config.DATA_DIR):
        return
    conn = _get_connection()
    migrated = 0
    for entry in os.listdir(config.DATA_DIR):
        profile_dir = os.path.join(config.DATA_DIR, entry)
        profile_file = os.path.join(profile_dir, "perfil.json")
        if not os.path.isfile(profile_file):
            continue
        slug = _sanitize_slug(entry)
        if conn.execute("SELECT 1 FROM profiles WHERE username = ?", (slug,)).fetchone():
            continue
        try:
            with open(profile_file, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        conn.execute(
            """INSERT INTO profiles
               (username, full_name, email, phone, linkedin_url, github_url,
                password_hash, salt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                slug, data.get("full_name", ""), data.get("email", ""),
                data.get("phone", ""), data.get("linkedin_url", ""),
                data.get("github_url", ""), data.get("password_hash", ""),
                data.get("salt", ""),
            ),
        )
        user_id = conn.execute(
            "SELECT id FROM profiles WHERE username = ?", (slug,)
        ).fetchone()["id"]

        kb_file = os.path.join(profile_dir, "base_conocimiento.md")
        if os.path.isfile(kb_file):
            with open(kb_file, encoding="utf-8") as f:
                kb = f.read().strip()
            if kb:
                conn.execute(
                    "INSERT INTO experiences (user_id, content) VALUES (?, ?)",
                    (user_id, kb),
                )

        skills_file = os.path.join(profile_dir, "habilidades.md")
        if os.path.isfile(skills_file):
            with open(skills_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    match = re.search(r"\*\*(.+?)\*\* -> \[(.+?)\]", line)
                    if match:
                        conn.execute(
                            "INSERT INTO skills (user_id, name, category) VALUES (?, ?, ?)",
                            (user_id, match.group(1), match.group(2)),
                        )

        edu_file = os.path.join(profile_dir, "educacion.md")
        if os.path.isfile(edu_file):
            with open(edu_file, encoding="utf-8") as f:
                content = f.read().strip()
            if content:
                entries = re.split(r"\n(?=### )", content)
                for entry_text in entries:
                    entry_text = entry_text.strip()
                    if entry_text:
                        conn.execute(
                            "INSERT INTO education_entries (user_id, content) VALUES (?, ?)",
                            (user_id, entry_text),
                        )

        migrated += 1
        logger.info("Migrated profile '%s' from flat files to DB.", slug)

    conn.commit()
    conn.close()
    if migrated:
        logger.info("Auto-migration complete: %d profile(s) imported.", migrated)


# ── profile CRUD ───────────────────────────────────────────────────


def list_profiles() -> list[str]:
    init_db()
    rows = _execute("SELECT username FROM profiles ORDER BY username")
    if not rows:
        _migrate_all_legacy_profiles()
        rows = _execute("SELECT username FROM profiles ORDER BY username")
    return [r["username"] for r in rows]


def load_profile(user_slug: str) -> dict | None:
    init_db()
    return _execute_one("SELECT * FROM profiles WHERE username = ?", (user_slug,))


def save_profile(user_slug: str, profile_data: dict) -> None:
    init_db()
    fields = (
        profile_data.get("full_name", ""),
        profile_data.get("email", ""),
        profile_data.get("phone", ""),
        profile_data.get("linkedin_url", ""),
        profile_data.get("github_url", ""),
        profile_data.get("password_hash", ""),
        profile_data.get("salt", ""),
        user_slug,
    )
    existing = _execute_one(
        "SELECT id FROM profiles WHERE username = ?", (user_slug,)
    )
    if existing:
        _execute(
            """UPDATE profiles SET full_name=?, email=?, phone=?,
               linkedin_url=?, github_url=?, password_hash=?, salt=?,
               updated_at=datetime('now')
               WHERE username=?""",
            fields,
        )
    else:
        _execute(
            """INSERT INTO profiles
               (full_name, email, phone, linkedin_url, github_url,
                password_hash, salt, username)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            fields,
        )


def delete_profile(user_slug: str) -> None:
    init_db()
    _execute("DELETE FROM profiles WHERE username = ?", (user_slug,))


def _ensure_profile(user_slug: str) -> None:
    _execute(
        "INSERT OR IGNORE INTO profiles (username) VALUES (?)", (user_slug,)
    )


_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def _date_to_key(text: str) -> int:
    text = text.strip().lower()
    if not text:
        return 0
    month = 1
    for name, num in _MONTHS.items():
        if name in text:
            month = num
            break
    years = re.findall(r"(\d{4})", text)
    year = int(years[0]) if years else 0
    return year * 100 + month if year else 0


def _extract_period_key(content: str) -> tuple[int, int]:
    for line in content.split("\n"):
        line = line.strip()
        if not line.startswith("### "):
            continue
        parts = [p.strip() for p in line[4:].split("|")]
        if len(parts) < 2:
            break
        period = parts[1]
        if "-" not in period:
            key = _date_to_key(period)
            return (key, key) if key else (0, 0)

        start_str, end_str = period.split("-", 1)
        end_str = end_str.strip()
        start_str = start_str.strip()

        if "presente" in end_str.lower() or "actual" in end_str.lower():
            end_key = 999999
        else:
            end_key = _date_to_key(end_str)

        start_key = _date_to_key(start_str)
        return (end_key, start_key)
    return (0, 0)


# ── knowledge base (experiences) ───────────────────────────────────


def read_knowledge_base(user_slug: str) -> str:
    init_db()
    _ensure_profile(user_slug)
    rows = _execute(
        """SELECT id, content FROM experiences
           WHERE user_id = (SELECT id FROM profiles WHERE username = ?)""",
        (user_slug,),
    )
    entries = [(r["content"], _extract_period_key(r["content"]), r["id"]) for r in rows]
    entries.sort(key=lambda x: (x[1], x[2]), reverse=True)
    return "\n\n".join(e[0] for e in entries)


def prepend_knowledge_base(user_slug: str, content: str) -> None:
    init_db()
    _ensure_profile(user_slug)
    _execute(
        """INSERT INTO experiences (user_id, content)
           VALUES ((SELECT id FROM profiles WHERE username = ?), ?)""",
        (user_slug, content),
    )


def overwrite_knowledge_base(user_slug: str, content: str) -> None:
    init_db()
    _ensure_profile(user_slug)
    _execute(
        "DELETE FROM experiences WHERE user_id = "
        "(SELECT id FROM profiles WHERE username = ?)",
        (user_slug,),
    )
    if content.strip():
        _execute(
            """INSERT INTO experiences (user_id, content)
               VALUES ((SELECT id FROM profiles WHERE username = ?), ?)""",
            (user_slug, content),
        )


def get_experience_list(user_slug: str) -> list[dict]:
    init_db()
    _ensure_profile(user_slug)
    rows = _execute(
        """SELECT id, content FROM experiences
           WHERE user_id = (SELECT id FROM profiles WHERE username = ?)""",
        (user_slug,),
    )
    entries = [{"id": r["id"], "content": r["content"]} for r in rows]
    entries.sort(
        key=lambda e: (_extract_period_key(e["content"]), e["id"]), reverse=True
    )
    return entries


def update_experience(experience_id: int, content: str) -> None:
    init_db()
    _execute(
        "UPDATE experiences SET content = ? WHERE id = ?",
        (content, experience_id),
    )


def delete_experience_entry(experience_id: int) -> None:
    init_db()
    _execute("DELETE FROM experiences WHERE id = ?", (experience_id,))


# ── skills ─────────────────────────────────────────────────────────


def read_skills(user_slug: str) -> str:
    return "".join(get_skills_lines(user_slug))


def get_skills_lines(user_slug: str) -> list[str]:
    init_db()
    _ensure_profile(user_slug)
    rows = _execute(
        """SELECT name, category FROM skills
           WHERE user_id = (SELECT id FROM profiles WHERE username = ?)
           ORDER BY created_at""",
        (user_slug,),
    )
    return [f"- **{r['name']}** -> [{r['category']}]\n" for r in rows]


def append_skill(user_slug: str, skill_line: str) -> None:
    match = re.search(r"\*\*(.+?)\*\* -> \[(.+?)\]", skill_line)
    if not match:
        return
    init_db()
    _ensure_profile(user_slug)
    _execute(
        """INSERT INTO skills (user_id, name, category)
           VALUES ((SELECT id FROM profiles WHERE username = ?), ?, ?)""",
        (user_slug, match.group(1), match.group(2)),
    )


def overwrite_skills(user_slug: str, lines: list[str]) -> None:
    init_db()
    _ensure_profile(user_slug)
    _execute(
        "DELETE FROM skills WHERE user_id = "
        "(SELECT id FROM profiles WHERE username = ?)",
        (user_slug,),
    )
    for line in lines:
        match = re.search(r"\*\*(.+?)\*\* -> \[(.+?)\]", line)
        if match:
            _execute(
                """INSERT INTO skills (user_id, name, category)
                   VALUES ((SELECT id FROM profiles WHERE username = ?), ?, ?)""",
                (user_slug, match.group(1), match.group(2)),
            )


# ── education ──────────────────────────────────────────────────────


def read_education(user_slug: str) -> str:
    init_db()
    _ensure_profile(user_slug)
    rows = _execute(
        """SELECT content FROM education_entries
           WHERE user_id = (SELECT id FROM profiles WHERE username = ?)
           ORDER BY id DESC""",
        (user_slug,),
    )
    return "\n".join(r["content"] for r in rows)


def prepend_education(user_slug: str, content: str) -> None:
    init_db()
    _ensure_profile(user_slug)
    _execute(
        """INSERT INTO education_entries (user_id, content)
           VALUES ((SELECT id FROM profiles WHERE username = ?), ?)""",
        (user_slug, content),
    )


def overwrite_education(user_slug: str, content: str) -> None:
    init_db()
    _ensure_profile(user_slug)
    _execute(
        "DELETE FROM education_entries WHERE user_id = "
        "(SELECT id FROM profiles WHERE username = ?)",
        (user_slug,),
    )
    if content.strip():
        for entry_text in content.split("\n"):
            entry_text = entry_text.strip()
            if entry_text:
                _execute(
                    """INSERT INTO education_entries (user_id, content)
                       VALUES ((SELECT id FROM profiles WHERE username = ?), ?)""",
                    (user_slug, entry_text),
                )


def delete_education_entry(user_slug: str, entry_index: int = 0) -> bool:
    init_db()
    _ensure_profile(user_slug)
    rows = _execute(
        """SELECT id FROM education_entries
           WHERE user_id = (SELECT id FROM profiles WHERE username = ?)
           ORDER BY id DESC""",
        (user_slug,),
    )
    if entry_index >= len(rows):
        return False
    _execute("DELETE FROM education_entries WHERE id = ?", (rows[entry_index]["id"],))
    return True


# ── data file checks ───────────────────────────────────────────────


def has_knowledge_base(user_slug: str) -> bool:
    init_db()
    row = _execute_one(
        "SELECT COUNT(*) AS cnt FROM experiences "
        "WHERE user_id = (SELECT id FROM profiles WHERE username = ?)",
        (user_slug,),
    )
    return row["cnt"] > 0 if row else False


def has_skills(user_slug: str) -> bool:
    init_db()
    row = _execute_one(
        "SELECT COUNT(*) AS cnt FROM skills "
        "WHERE user_id = (SELECT id FROM profiles WHERE username = ?)",
        (user_slug,),
    )
    return row["cnt"] > 0 if row else False


def has_education(user_slug: str) -> bool:
    init_db()
    row = _execute_one(
        "SELECT COUNT(*) AS cnt FROM education_entries "
        "WHERE user_id = (SELECT id FROM profiles WHERE username = ?)",
        (user_slug,),
    )
    return row["cnt"] > 0 if row else False


def all_data_files_exist(user_slug: str) -> bool:
    return has_knowledge_base(user_slug) and has_skills(user_slug) and has_education(user_slug)


# ── legacy migration stub ──────────────────────────────────────────


def migrate_legacy_data(user_slug: str) -> int:
    if _is_turso():
        return 0
    data_dir = os.path.join(config.DATA_DIR, user_slug)
    if not os.path.isdir(data_dir):
        return 0
    return 1


# ── utilities ──────────────────────────────────────────────────────


def _sanitize_slug(user_slug: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-]", "", user_slug)
