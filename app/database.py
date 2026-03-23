import sys
import sqlite3
from datetime import datetime
from pathlib import Path

# ── データベースファイルのパス ──────────────────────
if getattr(sys, "frozen", False):
    DB_PATH = Path(sys.executable).resolve().parent / "app" / "cove.db"
else:
    DB_PATH = Path(__file__).resolve().parent / "cove.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """データベースとテーブルを初期化する。アプリ起動時に1回だけ呼び出す。"""
    with get_connection() as conn:

        # ── カテゴリテーブル ──────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT    NOT NULL UNIQUE,
                color      TEXT    NOT NULL DEFAULT '#6B7280',
                created_at TEXT    NOT NULL
            )
        """)

        # デフォルトカテゴリ「未分類」を挿入（なければ）
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("""
            INSERT OR IGNORE INTO categories (id, name, color, created_at)
            VALUES (1, '未分類', '#6B7280', ?)
        """, (now,))

        # ── 録音テーブル ──────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS recordings (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                title               TEXT    NOT NULL DEFAULT '無題',
                memo                TEXT    NOT NULL DEFAULT '',
                wav_file            TEXT    NOT NULL DEFAULT '',
                transcript          TEXT    NOT NULL DEFAULT '',
                transcript_status   TEXT    NOT NULL DEFAULT 'pending',
                cleaned_transcript  TEXT    NOT NULL DEFAULT '',
                cleaning_status     TEXT    NOT NULL DEFAULT 'pending',
                ai_summary          TEXT    NOT NULL DEFAULT '',
                summary_status      TEXT    NOT NULL DEFAULT 'pending',
                category_id         INTEGER NOT NULL DEFAULT 1
                                    REFERENCES categories(id) ON UPDATE CASCADE,
                created_at          TEXT    NOT NULL,
                updated_at          TEXT    NOT NULL
            )
        """)

        # ── マイグレーション（既存DBへの対応） ────────
        migrations = [
            ("transcript_status",  "'pending'"),
            ("cleaned_transcript", "''"),
            ("cleaning_status",    "'pending'"),
            ("summary_status",     "'pending'"),
            ("category_id",        "1"),
        ]
        for col, default in migrations:
            try:
                conn.execute(f"ALTER TABLE recordings ADD COLUMN {col} TEXT NOT NULL DEFAULT {default}")
                print(f"[database] マイグレーション: {col} カラムを追加")
            except Exception:
                pass

        # 既存レコードのステータスを内容に基づいて設定
        conn.execute("""
            UPDATE recordings SET transcript_status = 'done'
            WHERE transcript != '' AND transcript_status = 'pending'
        """)
        conn.execute("""
            UPDATE recordings SET cleaning_status = 'done', cleaned_transcript = transcript
            WHERE transcript != '' AND cleaning_status = 'pending'
        """)
        conn.execute("""
            UPDATE recordings SET ai_summary = '', summary_status = 'pending'
            WHERE ai_summary LIKE '%Ollama導入後%'
               OR ai_summary LIKE '%現在要約は行いません%'
               OR ai_summary LIKE '%要約にはGroq APIキー%'
        """)
        conn.execute("""
            UPDATE recordings SET summary_status = 'done'
            WHERE ai_summary != '' AND summary_status = 'pending'
        """)


        # ── 保管庫：テキストメモテーブル ─────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS vault_memos (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT    NOT NULL DEFAULT '',
                body        TEXT    NOT NULL DEFAULT '',
                category_id INTEGER NOT NULL DEFAULT 1
                            REFERENCES categories(id) ON UPDATE CASCADE,
                created_at  TEXT    NOT NULL,
                updated_at  TEXT    NOT NULL
            )
        """)

        # ── 保管庫：ファイルテーブル ──────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS vault_files (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                filename      TEXT    NOT NULL,
                original_name TEXT    NOT NULL,
                filetype      TEXT    NOT NULL,
                summary       TEXT    NOT NULL DEFAULT '',
                summary_status TEXT   NOT NULL DEFAULT 'pending',
                category_id   INTEGER NOT NULL DEFAULT 1
                              REFERENCES categories(id) ON UPDATE CASCADE,
                created_at    TEXT    NOT NULL
            )
        """)
        # ── 相談室：ペルソナ設定テーブル ─────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS persona_settings (
                persona_name TEXT PRIMARY KEY,
                enabled      INTEGER NOT NULL DEFAULT 1
            )
        """)

        # デフォルトペルソナを挿入（なければ）
        default_personas = [
            "戦略家", "リスク管理者", "アナリスト", "クリエイター",
            "法務・コンプラ", "ユーザー視点", "クレーマー", "マーケッター",
        ]
        for name in default_personas:
            conn.execute(
                "INSERT OR IGNORE INTO persona_settings (persona_name, enabled) VALUES (?, 1)",
                (name,)
            )

        # ── 相談室：セッションテーブル ────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS council_sessions (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                question       TEXT    NOT NULL DEFAULT '',
                category_id    INTEGER NOT NULL DEFAULT 1
                               REFERENCES categories(id) ON UPDATE CASCADE,
                final_decision TEXT    NOT NULL DEFAULT '',
                created_at     TEXT    NOT NULL
            )
        """)

        # ── 相談室：採用回答テーブル ──────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS council_adopted (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id   INTEGER NOT NULL
                             REFERENCES council_sessions(id) ON DELETE CASCADE,
                persona_name TEXT    NOT NULL,
                answer       TEXT    NOT NULL DEFAULT '',
                created_at   TEXT    NOT NULL
            )
        """)

        conn.commit()
    print("[database] 初期化完了")


# ══════════════════════════════════════════════════
#  カテゴリ操作
# ══════════════════════════════════════════════════

def get_all_categories() -> list[dict]:
    """全カテゴリを返す"""
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM categories ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def create_category(name: str, color: str) -> dict:
    """カテゴリを新規作成する"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO categories (name, color, created_at) VALUES (?, ?, ?)",
                (name.strip(), color, now)
            )
            conn.commit()
        print(f"[database] カテゴリ作成: {name}")
        return {"status": "ok", "id": cursor.lastrowid}
    except sqlite3.IntegrityError:
        return {"status": "error", "message": f"カテゴリ名 '{name}' はすでに存在します"}


def update_category(category_id: int, name: str, color: str) -> dict:
    """カテゴリ名・色を更新する（紐づくデータは外部キーのON UPDATE CASCADEで自動更新）"""
    if category_id == 1:
        return {"status": "error", "message": "未分類は変更できません"}
    try:
        with get_connection() as conn:
            conn.execute(
                "UPDATE categories SET name = ?, color = ? WHERE id = ?",
                (name.strip(), color, category_id)
            )
            conn.commit()
        print(f"[database] カテゴリ更新: id={category_id} name={name}")
        return {"status": "ok"}
    except sqlite3.IntegrityError:
        return {"status": "error", "message": f"カテゴリ名 '{name}' はすでに存在します"}


def delete_category(category_id: int) -> dict:
    """カテゴリを削除し、紐づくデータを未分類(id=1)に移動する"""
    if category_id == 1:
        return {"status": "error", "message": "未分類は削除できません"}
    with get_connection() as conn:
        # 紐づくデータを未分類に移動
        conn.execute(
            "UPDATE recordings SET category_id = 1 WHERE category_id = ?",
            (category_id,)
        )
        conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
        conn.commit()
    print(f"[database] カテゴリ削除: id={category_id}")
    return {"status": "ok"}


def delete_recordings_by_category(category_id: int) -> int:
    """指定カテゴリの録音データをすべて削除し削除件数を返す"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id FROM recordings WHERE category_id = ?", (category_id,)
        ).fetchall()
        count = len(rows)
        conn.execute("DELETE FROM recordings WHERE category_id = ?", (category_id,))
        conn.commit()
    print(f"[database] カテゴリ({category_id})の録音を削除: {count}件")
    return count


# ══════════════════════════════════════════════════
#  録音操作
# ══════════════════════════════════════════════════

def create_recording(wav_file: str, title: str = "無題", memo: str = "", category_id: int = 1) -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO recordings
              (title, memo, wav_file, transcript_status, cleaning_status, summary_status, category_id, created_at, updated_at)
            VALUES (?, ?, ?, 'pending', 'pending', 'pending', ?, ?, ?)
            """,
            (title, memo, wav_file, category_id, now, now),
        )
        conn.commit()
    print(f"[database] 作成: id={cursor.lastrowid}, wav={wav_file}")
    return cursor.lastrowid


def get_all_recordings(category_id: int = None) -> list[dict]:
    """全録音データを新しい順で返す。category_idを指定するとフィルタリング"""
    with get_connection() as conn:
        if category_id is not None:
            rows = conn.execute(
                "SELECT * FROM recordings WHERE category_id = ? ORDER BY created_at DESC",
                (category_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM recordings ORDER BY created_at DESC"
            ).fetchall()
    return [_recording_to_dict(row) for row in rows]


def get_recording(record_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM recordings WHERE id = ?", (record_id,)
        ).fetchone()
    return _recording_to_dict(row) if row else None


def _recording_to_dict(row) -> dict:
    """Rowオブジェクトを辞書に変換（後方互換性のためのフォールバック付き）"""
    keys = row.keys()
    d = dict(row)
    d.setdefault("transcript_status",  "pending")
    d.setdefault("cleaned_transcript", "")
    d.setdefault("cleaning_status",    "pending")
    d.setdefault("summary_status",     "pending")
    d.setdefault("category_id",        1)
    return d


def update_transcript_and_summary(record_id: int, transcript: str, ai_summary: str) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    t_status = "done" if transcript else "error"
    s_status = "done" if ai_summary and "Ollama導入後" not in ai_summary and "現在要約は行いません" not in ai_summary else "pending"
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE recordings
            SET transcript = ?, ai_summary = ?,
                transcript_status = ?, summary_status = ?, updated_at = ?
            WHERE id = ?
            """,
            (transcript, ai_summary, t_status, s_status, now, record_id),
        )
        conn.commit()
    print(f"[database] 文字起こし・要約を保存: id={record_id} (transcript:{t_status}, summary:{s_status})")


def update_cleaned_transcript(record_id: int, cleaned_transcript: str) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "done" if cleaned_transcript else "error"
    with get_connection() as conn:
        conn.execute(
            "UPDATE recordings SET cleaned_transcript = ?, cleaning_status = ?, updated_at = ? WHERE id = ?",
            (cleaned_transcript, status, now, record_id),
        )
        conn.commit()
    print(f"[database] クリーニング結果を保存: id={record_id} (status:{status})")


def update_title_and_memo(record_id: int, title: str, memo: str) -> dict:
    if not title.strip():
        return {"status": "error", "message": "タイトルは必須です"}
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        conn.execute(
            "UPDATE recordings SET title = ?, memo = ?, updated_at = ? WHERE id = ?",
            (title.strip(), memo.strip(), now, record_id),
        )
        conn.commit()
    print(f"[database] タイトル・メモを更新: id={record_id}")
    return {"status": "updated"}


def update_recording_category(record_id: int, category_id: int) -> dict:
    """録音のカテゴリを更新する"""
    with get_connection() as conn:
        conn.execute(
            "UPDATE recordings SET category_id = ?, updated_at = ? WHERE id = ?",
            (category_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), record_id),
        )
        conn.commit()
    return {"status": "updated"}


def delete_recording(record_id: int) -> dict:
    record = get_recording(record_id)
    if not record:
        return {"status": "error", "message": "データが見つかりません"}
    with get_connection() as conn:
        conn.execute("DELETE FROM recordings WHERE id = ?", (record_id,))
        conn.commit()
    print(f"[database] 削除: id={record_id}")
    return {"status": "deleted", "wav_file": record["wav_file"]}


def delete_all_recordings() -> int:
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM recordings").fetchone()[0]
        conn.execute("DELETE FROM recordings")
        conn.commit()
    print(f"[database] 全録音削除: {count}件")
    return count

# ══════════════════════════════════════════════════
#  保管庫：テキストメモ操作
# ══════════════════════════════════════════════════

def get_all_vault_memos(category_id: int = None) -> list[dict]:
    with get_connection() as conn:
        if category_id is not None:
            rows = conn.execute(
                "SELECT * FROM vault_memos WHERE category_id = ? ORDER BY created_at DESC",
                (category_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM vault_memos ORDER BY created_at DESC"
            ).fetchall()
    return [dict(r) for r in rows]


def create_vault_memo(title: str, body: str, category_id: int = 1) -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO vault_memos (title, body, category_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (title.strip(), body.strip(), category_id, now, now)
        )
        conn.commit()
    print(f"[database] 保管庫メモ作成: id={cursor.lastrowid}")
    return cursor.lastrowid


def update_vault_memo(memo_id: int, title: str, body: str, category_id: int) -> dict:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        conn.execute(
            "UPDATE vault_memos SET title=?, body=?, category_id=?, updated_at=? WHERE id=?",
            (title.strip(), body.strip(), category_id, now, memo_id)
        )
        conn.commit()
    return {"status": "ok"}


def delete_vault_memo(memo_id: int) -> dict:
    with get_connection() as conn:
        conn.execute("DELETE FROM vault_memos WHERE id=?", (memo_id,))
        conn.commit()
    print(f"[database] 保管庫メモ削除: id={memo_id}")
    return {"status": "ok"}


# ══════════════════════════════════════════════════
#  保管庫：ファイル操作
# ══════════════════════════════════════════════════

def get_all_vault_files(category_id: int = None) -> list[dict]:
    with get_connection() as conn:
        if category_id is not None:
            rows = conn.execute(
                "SELECT * FROM vault_files WHERE category_id = ? ORDER BY created_at DESC",
                (category_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM vault_files ORDER BY created_at DESC"
            ).fetchall()
    return [dict(r) for r in rows]


def create_vault_file(filename: str, original_name: str, filetype: str, category_id: int = 1) -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO vault_files
               (filename, original_name, filetype, summary, summary_status, category_id, created_at)
               VALUES (?, ?, ?, '', 'pending', ?, ?)""",
            (filename, original_name, filetype, category_id, now)
        )
        conn.commit()
    print(f"[database] 保管庫ファイル作成: id={cursor.lastrowid} name={original_name}")
    return cursor.lastrowid


def update_vault_file_summary(file_id: int, summary: str) -> None:
    status = "done" if summary else "error"
    with get_connection() as conn:
        conn.execute(
            "UPDATE vault_files SET summary=?, summary_status=? WHERE id=?",
            (summary, status, file_id)
        )
        conn.commit()
    print(f"[database] 保管庫ファイル要約保存: id={file_id}")


def delete_vault_file(file_id: int) -> dict:
    with get_connection() as conn:
        row = conn.execute("SELECT filename FROM vault_files WHERE id=?", (file_id,)).fetchone()
        if not row:
            return {"status": "error", "message": "ファイルが見つかりません"}
        conn.execute("DELETE FROM vault_files WHERE id=?", (file_id,))
        conn.commit()
    print(f"[database] 保管庫ファイル削除: id={file_id}")
    return {"status": "ok", "filename": row["filename"]}


def delete_vault_items_by_category(category_id: int) -> int:
    """指定カテゴリの保管庫データ（メモ・ファイル）を全削除"""
    with get_connection() as conn:
        memo_count = conn.execute(
            "SELECT COUNT(*) FROM vault_memos WHERE category_id=?", (category_id,)
        ).fetchone()[0]
        file_count = conn.execute(
            "SELECT COUNT(*) FROM vault_files WHERE category_id=?", (category_id,)
        ).fetchone()[0]
        conn.execute("DELETE FROM vault_memos WHERE category_id=?", (category_id,))
        conn.execute("DELETE FROM vault_files WHERE category_id=?", (category_id,))
        conn.commit()
    return memo_count + file_count


# ══════════════════════════════════════════════════
#  相談室：ペルソナ設定操作
# ══════════════════════════════════════════════════

def get_all_persona_settings() -> list[dict]:
    """全ペルソナ設定を返す"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT persona_name, enabled FROM persona_settings ORDER BY rowid"
        ).fetchall()
    return [dict(r) for r in rows]


def update_persona_enabled(persona_name: str, enabled: bool) -> dict:
    """ペルソナのON/OFFを更新する"""
    with get_connection() as conn:
        conn.execute(
            "UPDATE persona_settings SET enabled = ? WHERE persona_name = ?",
            (1 if enabled else 0, persona_name)
        )
        conn.commit()
    return {"status": "ok"}


# ══════════════════════════════════════════════════
#  相談室：セッション操作
# ══════════════════════════════════════════════════

def create_council_session(question: str, category_id: int, final_decision: str = "") -> int:
    """相談セッションを作成し、IDを返す"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO council_sessions (question, category_id, final_decision, created_at) VALUES (?, ?, ?, ?)",
            (question.strip(), category_id, final_decision.strip(), now)
        )
        conn.commit()
    print(f"[database] 相談セッション作成: id={cursor.lastrowid}")
    return cursor.lastrowid


def update_council_session_decision(session_id: int, final_decision: str) -> dict:
    """最終判断メモを更新する"""
    with get_connection() as conn:
        conn.execute(
            "UPDATE council_sessions SET final_decision = ? WHERE id = ?",
            (final_decision.strip(), session_id)
        )
        conn.commit()
    return {"status": "ok"}


def create_council_adopted(session_id: int, persona_name: str, answer: str) -> int:
    """採用した回答を保存する"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO council_adopted (session_id, persona_name, answer, created_at) VALUES (?, ?, ?, ?)",
            (session_id, persona_name, answer.strip(), now)
        )
        conn.commit()
    print(f"[database] 採用回答保存: session={session_id} persona={persona_name}")
    return cursor.lastrowid


def get_council_sessions(category_id: int = None, limit: int = 20) -> list[dict]:
    """相談履歴を返す（採用回答も含む）"""
    with get_connection() as conn:
        if category_id is not None:
            sessions = conn.execute(
                "SELECT * FROM council_sessions WHERE category_id = ? ORDER BY created_at DESC LIMIT ?",
                (category_id, limit)
            ).fetchall()
        else:
            sessions = conn.execute(
                "SELECT * FROM council_sessions ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()

        result = []
        for s in sessions:
            s_dict = dict(s)
            adopted = conn.execute(
                "SELECT persona_name, answer FROM council_adopted WHERE session_id = ? ORDER BY created_at",
                (s_dict["id"],)
            ).fetchall()
            s_dict["adopted"] = [dict(a) for a in adopted]
            result.append(s_dict)
    return result


def get_context_for_category(category_id: int) -> dict:
    """指定カテゴリに紐づくコンテキストデータを収集する"""
    with get_connection() as conn:
        recordings = conn.execute(
            "SELECT id, title, ai_summary FROM recordings WHERE category_id = ? AND ai_summary != '' ORDER BY created_at DESC LIMIT 10",
            (category_id,)
        ).fetchall()
        memos = conn.execute(
            "SELECT id, title, body FROM vault_memos WHERE category_id = ? ORDER BY created_at DESC LIMIT 10",
            (category_id,)
        ).fetchall()
        files = conn.execute(
            "SELECT id, original_name, summary FROM vault_files WHERE category_id = ? AND summary != '' ORDER BY created_at DESC LIMIT 10",
            (category_id,)
        ).fetchall()
        sessions = conn.execute(
            """SELECT cs.question, cs.final_decision, ca.persona_name, ca.answer
               FROM council_sessions cs
               LEFT JOIN council_adopted ca ON ca.session_id = cs.id
               WHERE cs.category_id = ?
               ORDER BY cs.created_at DESC LIMIT 5""",
            (category_id,)
        ).fetchall()

    return {
        "recordings": [dict(r) for r in recordings],
        "memos":      [dict(m) for m in memos],
        "files":      [dict(f) for f in files],
        "sessions":   [dict(s) for s in sessions],
    }
