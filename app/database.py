import sys
import sqlite3
from datetime import datetime
from pathlib import Path

# ── データベースファイルのパス ──────────────────────
# PyInstallerで固めた場合は実行ファイルと同じ場所に保存
if getattr(sys, "frozen", False):
    DB_PATH = Path(sys.executable).resolve().parent / "aura.db"
else:
    DB_PATH = Path(__file__).resolve().parent / "aura.db"


def get_connection() -> sqlite3.Connection:
    """データベースへの接続を返す"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row  # 結果を辞書形式で取得できるようにする
    return conn


def init_db() -> None:
    """
    データベースとテーブルを初期化する。
    アプリ起動時に1回だけ呼び出す。
    テーブルが既に存在する場合は何もしない。
    """
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS recordings (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                title               TEXT    NOT NULL DEFAULT '無題',
                memo                TEXT    NOT NULL DEFAULT '',
                transcript          TEXT    NOT NULL DEFAULT '',
                ai_summary          TEXT    NOT NULL DEFAULT '',
                wav_file            TEXT    NOT NULL DEFAULT '',
                transcript_status   TEXT    NOT NULL DEFAULT 'pending',
                summary_status      TEXT    NOT NULL DEFAULT 'pending',
                created_at          TEXT    NOT NULL,
                updated_at          TEXT    NOT NULL
            )
        """)
        # 既存DBへのマイグレーション（カラムがなければ追加）
        for col, default in [
            ("transcript_status", "'pending'"),
            ("summary_status",    "'pending'"),
        ]:
            try:
                conn.execute(f"ALTER TABLE recordings ADD COLUMN {col} TEXT NOT NULL DEFAULT {default}")
                print(f"[database] マイグレーション: {col} カラムを追加")
            except Exception:
                pass  # すでに存在する場合はスキップ
        # 既存レコードのフラグを内容に基づいて設定
        conn.execute("""
            UPDATE recordings
            SET transcript_status = 'done'
            WHERE transcript != '' AND transcript_status = 'pending'
        """)
        # 古いスキップメッセージをクリア
        conn.execute("""
            UPDATE recordings
            SET ai_summary = '', summary_status = 'pending'
            WHERE ai_summary LIKE '%Ollama導入後%'
               OR ai_summary LIKE '%現在要約は行いません%'
               OR ai_summary LIKE '%要約にはGroq APIキー%'
        """)
        conn.execute("""
            UPDATE recordings
            SET summary_status = 'done'
            WHERE ai_summary != '' AND summary_status = 'pending'
        """)
        conn.commit()
    print("[database] 初期化完了")


# ── 作成 ──────────────────────────────────────────
def create_recording(
    wav_file: str,
    title: str = "無題",
    memo: str = "",
) -> int:
    """
    録音データを新規登録する。
    Returns:
        作成されたレコードの id
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO recordings (title, memo, transcript, ai_summary, wav_file, transcript_status, summary_status, created_at, updated_at)
            VALUES (?, ?, '', '', ?, 'pending', 'pending', ?, ?)
            """,
            (title, memo, wav_file, now, now),
        )
        conn.commit()
        record_id = cursor.lastrowid
    print(f"[database] 作成: id={record_id}, wav={wav_file}")
    return record_id


# ── 読み取り ──────────────────────────────────────
def get_all_recordings() -> list[dict]:
    """
    全録音データを新しい順で返す。
    Returns:
        [{"id": int, "title": str, ...}, ...]
    """
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM recordings ORDER BY created_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def get_recording(record_id: int) -> dict | None:
    """
    指定IDの録音データを返す。
    Returns:
        {"id": int, "title": str, ...} or None
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM recordings WHERE id = ?", (record_id,)
        ).fetchone()
    return dict(row) if row else None


# ── 更新 ──────────────────────────────────────────
def update_transcript_and_summary(
    record_id: int,
    transcript: str,
    ai_summary: str,
) -> None:
    """文字起こしと要約を保存する（録音停止後に自動で呼び出す）"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    t_status = "done" if transcript else "error"
    s_status = "done" if ai_summary and "Ollama導入後" not in ai_summary and "現在要約は行いません" not in ai_summary else "pending"
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE recordings
            SET transcript = ?, ai_summary = ?,
                transcript_status = ?, summary_status = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (transcript, ai_summary, t_status, s_status, now, record_id),
        )
        conn.commit()
    print(f"[database] 文字起こし・要約を保存: id={record_id} (transcript:{t_status}, summary:{s_status})")


def update_title_and_memo(
    record_id: int,
    title: str,
    memo: str,
) -> dict:
    """
    タイトルと概要メモを更新する（index画面・一覧から編集可能）。
    Returns:
        {"status": "updated"} or {"status": "error", "message": str}
    """
    if not title.strip():
        return {"status": "error", "message": "タイトルは必須です"}

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE recordings
            SET title = ?, memo = ?, updated_at = ?
            WHERE id = ?
            """,
            (title.strip(), memo.strip(), now, record_id),
        )
        conn.commit()
    print(f"[database] タイトル・メモを更新: id={record_id}")
    return {"status": "updated"}


# ── 削除 ──────────────────────────────────────────
def delete_recording(record_id: int) -> dict:
    """
    指定IDの録音データをDBから削除する。
    ※ WAVファイルの削除は recorder.py の delete_recording() で行う。
    Returns:
        {"status": "deleted", "wav_file": str} or {"status": "error", "message": str}
    """
    record = get_recording(record_id)
    if not record:
        return {"status": "error", "message": "データが見つかりません"}

    with get_connection() as conn:
        conn.execute("DELETE FROM recordings WHERE id = ?", (record_id,))
        conn.commit()
    print(f"[database] 削除: id={record_id}")
    return {"status": "deleted", "wav_file": record["wav_file"]}
