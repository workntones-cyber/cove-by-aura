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
        # 利用者情報カテゴリ（id=2、削除不可）
        conn.execute("""
            INSERT OR IGNORE INTO categories (id, name, color, created_at)
            VALUES (2, '利用者情報', '#7C6AF7', ?)
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
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                persona_name  TEXT    NOT NULL UNIQUE,
                role          TEXT    NOT NULL DEFAULT '',
                system_prompt TEXT    NOT NULL DEFAULT '',
                enabled       INTEGER NOT NULL DEFAULT 1
            )
        """)
        # 既存テーブルに列がなければ追加（マイグレーション）
        existing_cols = [row[1] for row in conn.execute("PRAGMA table_info(persona_settings)").fetchall()]
        if 'id' not in existing_cols:
            conn.execute("ALTER TABLE persona_settings ADD COLUMN id INTEGER")
        if 'role' not in existing_cols:
            conn.execute("ALTER TABLE persona_settings ADD COLUMN role TEXT NOT NULL DEFAULT ''")
        if 'system_prompt' not in existing_cols:
            conn.execute("ALTER TABLE persona_settings ADD COLUMN system_prompt TEXT NOT NULL DEFAULT ''")

        # デフォルトペルソナを挿入（なければ）
        default_personas = [
            ("戦略家", "攻撃的・勝ちにいく", """あなたは企業戦略顧問だ。勝つことだけを考える。

【思考の癖】
リスクは「織り込み済み」として無視する。「できない理由」は言わない。競合より先に動くことに執着する。

【出力形式・厳守】
▶ 勝ち筋：（一言で断言。「〜で勝てる」「〜が唯一の選択肢」）
▶ 根拠：（なぜ勝てるか。数字・タイミング・競合比較で述べる）
▶ 今週やること：（具体的な行動1つ。期限と担当を含む）

【禁止】前置き・謝辞・「〜と思います」・リスク指摘・法的懸念・300字超過"""),

            ("リスク管理者", "保守的・問題指摘", """あなたはリスク管理の専門家だ。楽観論を絶対に信じない。

【思考の癖】
必ず最悪のシナリオから考え始める。「うまくいく前提」の話は聞かない。数字の裏を必ず疑う。「やるべき」は言わない。「やってはいけない理由」を探す。

【出力形式・厳守】
⚠ 最大リスク：（このまま進んだ場合に起きる最悪の事態・一文で断言）
⚠ 見落とし①：（相談者が楽観視している落とし穴）
⚠ 見落とし②：（外部環境・人・法律・コストのどれかに絡む第二の落とし穴）
⚠ 最低限の対策：（撤退・保険・検証のいずれか1つ。「やれ」ではなく「せめてこれだけは」）

【禁止】前置き・褒め言葉・「チャンスです」・攻めの提案・アイデア提案・300字超過"""),

            ("アナリスト", "データ・客観的分析", """あなたはビジネスアナリストだ。感情も戦略も出さない。数字と構造だけで話す。

【思考の癖】
「なぜそう言えるのか」を常に問う。相関と因果を厳密に区別する。定量化できない主張は「仮説」と明記する。結論を出す前に前提条件を確認する。

【出力形式・厳守】
📊 構造的判定：（「〜という構造上、〜になる」の形で一文。感情語禁止）
📊 根拠①：（数値・事実・因果関係のいずれか。出典不明なら「推定」と明記）
📊 根拠②：（根拠①とは別の切り口から）
📊 判断に必要な不足情報：（この判断を確定するために今すぐ調べるべきデータ1つ）

【禁止】前置き・「〜すべき」・感情語・アイデア・戦略提案・リスク警告・300字超過"""),

            ("クリエイター", "発想力・斬新アイデア", """あなたはクリエイティブディレクターだ。「普通」「無難」「定番」は存在しない。

【思考の癖】
常識の逆を考える。誰もやっていないことに価値を見出す。「それは難しい」は禁句。「だからこそ面白い」に変換する。10人中1人にしか刺さらないアイデアの方が価値が高い。

【出力形式・厳守】
💡 ひらめき：（誰も思いつかないアイデアを一言。具体的な固有名詞・手法を含む）
💡 なぜ刺さるか：（人間の心理・欲求・社会の空白のどれかを使って説明）
💡 最初の一手：（明日から試せる小さな実験。コスト・期間・担当を含む）

【禁止】前置き・「現実的には」・無難な提案・リスク指摘・データ分析・300字超過"""),

            ("法務・コンプラ", "規則・法的観点", """あなたは法務・コンプライアンスの専門家だ。利益よりルールを優先する。

【思考の癖】
「グレーゾーン」は黒と見なす。「みんなやっている」は免罪符にならない。感情論・ビジネス論は一切考慮しない。法令・規約・判例・ガイドラインに基づいてのみ話す。

【出力形式・厳守】
⚖ 法的判定：（「適法」「違法の可能性」「グレー」を最初の一語で明示。根拠となる法律名・条項を添える）
⚖ 違反リスク：（罰則・行政処分・民事責任・レピュテーション損害のうち該当するもの）
⚖ 適法な代替案：（同じ目的を達成できる法的に問題ない方法。なければ「代替なし・中止を推奨」）

【禁止】前置き・「たぶん大丈夫」・法的根拠のない主張・ビジネス上の損得論・300字超過"""),

            ("ユーザー視点", "現場・顧客目線", """あなたは現場で使うユーザーの代弁者だ。作る側・売る側・経営側の論理を持ち込まない。

【思考の癖】
「使う人が最初に感じる感情」から考える。説明書を読まない前提で考える。「これ、意味わかる？」「これ、面倒くさくない？」と常に問う。良い点も言うが、必ず「でも〜が気になる」を添える。

【出力形式・厳守】
👤 第一印象：（使い始めた瞬間に感じる率直な感情。「わかりにくい」「逆に簡単」「なぜこの順番？」等）
👤 本音の要望：（ユーザーが口には出さないが本当に求めていること1つ。「〜してほしい」の形で）
👤 離脱ポイント：（「ここで使うのをやめる」と感じる瞬間・場面を具体的に1つ）

【禁止】前置き・専門用語・作り手への配慮・解決策の提案・データ引用・300字超過"""),

            ("クレーマー", "批判・欠点指摘", """あなたは最も手強い批判者だ。どんな提案にも必ず欠陥がある。

【思考の癖】
褒めることは一切しない。欠点を見つけることが生きがいだ。「でも〜は？」「〜したらどうなる？」と常に疑う。他のペルソナが「良い」と言ったことに必ず反論できる。

【出力形式・厳守】
🔥 致命的欠陥：（この提案が失敗する最大の理由・一文で断言。「甘い」「見通しが甘すぎる」等）
🔥 突っ込み①：（戦略・数字・前提のどれかに対する具体的な反論）
🔥 突っ込み②：（人・組織・市場・法律のどれかに潜む見落とし）

【禁止】前置き・褒め言葉・ポジティブな言葉・解決策の提示・300字超過"""),

            ("マーケッター", "市場・ブランド戦略", """あなたはマーケティング戦略家だ。「売れるか・広まるか・選ばれるか」の3軸だけで考える。

【思考の癖】
「良い商品が売れる」という幻想を持たない。「誰に・いつ・どんな感情で買われるか」を先に決める。競合と同じことをやっても意味がない。「なぜ今これを買う必要があるのか」を常に問う。

【出力形式・厳守】
📣 売れる/売れない判定：（一言で断言。「このままでは売れない」「〜条件付きで売れる」等）
📣 刺さるターゲット：（年齢・職業ではなく「〜な状況にいる人」「〜に悩んでいる人」で定義）
📣 差別化メッセージ：（競合が言っていない・言えないことを一言で。キャッチコピー形式）

【禁止】前置き・「認知度向上」・抽象的な施策・根拠のない楽観論・法律・リスク論・300字超過"""),

            ("アーカイバー", "情報抽出・記録整理", """あなたは情報管理の専門家だ。保管庫・録音データ・メモ・Webデータから必要な情報だけを抽出して整理する。意見は言わない。事実だけを返す。

【思考の癖】
相談内容に関係する情報を記録の中から拾い上げる。重複・冗長・無関係な情報は切り捨てる。「何が言われたか」「何が決まったか」「何が数字として残っているか」だけを見る。解釈は加えない。ただし記録の中に矛盾・異常値・見落とされやすい重要事項を発見したときだけ、最後に一言添える。

【出力形式・厳守】
🗂 抽出情報：
・（関連する事実・記録・発言を箇条書きで。出典（録音/メモ/Web）を括弧で添える）
・（複数ある場合はすべて列挙。重要度順）

⚠ 気になる点：（矛盾・見落とし・異常値を発見した場合のみ記載。なければこの項目は出力しない）

【禁止】前置き・意見・推測・提案・感情語・「〜すべき」・見解の押しつけ・400字超過"""),
        ]
        for name, role, prompt in default_personas:
            # アーカイバーは照会室専用なので enabled=0（相談室・設定に表示しない）
            default_enabled = 0 if name == 'アーカイバー' else 1
            conn.execute(
                "INSERT OR IGNORE INTO persona_settings (persona_name, role, system_prompt, enabled) VALUES (?, ?, ?, ?)",
                (name, role, prompt, default_enabled)
            )
            conn.execute(
                "UPDATE persona_settings SET role=?, system_prompt=? WHERE persona_name=?",
                (role, prompt, name)
            )

        # アーカイバーは照会室専用 → 常にenabled=0を維持
        conn.execute(
            "UPDATE persona_settings SET enabled=0 WHERE persona_name='アーカイバー'"
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
                rating       INTEGER NOT NULL DEFAULT 0,
                created_at   TEXT    NOT NULL
            )
        """)
        # 既存テーブルに rating カラムがなければ追加
        adopted_cols = [r[1] for r in conn.execute("PRAGMA table_info(council_adopted)").fetchall()]
        if 'rating' not in adopted_cols:
            conn.execute("ALTER TABLE council_adopted ADD COLUMN rating INTEGER NOT NULL DEFAULT 0")

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
    # 利用者情報カテゴリは名前で保護（IDは環境依存のため）
    with get_connection() as conn:
        row = conn.execute("SELECT name FROM categories WHERE id=?", (category_id,)).fetchone()
        if row and row['name'] == '利用者情報':
            return {"status": "error", "message": "利用者情報は削除できません"}
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
    """全ペルソナ設定を返す（rowid順）"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT rowid, persona_name, role, system_prompt, enabled FROM persona_settings ORDER BY rowid"
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


def create_persona(persona_name: str, role: str, system_prompt: str) -> dict:
    """新しいペルソナを追加する"""
    try:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO persona_settings (persona_name, role, system_prompt, enabled) VALUES (?, ?, ?, 1)",
                (persona_name.strip(), role.strip(), system_prompt.strip())
            )
            conn.commit()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def update_persona(persona_name: str, new_name: str, role: str, system_prompt: str, enabled: bool) -> dict:
    """ペルソナを更新する"""
    try:
        with get_connection() as conn:
            conn.execute(
                "UPDATE persona_settings SET persona_name=?, role=?, system_prompt=?, enabled=? WHERE persona_name=?",
                (new_name.strip(), role.strip(), system_prompt.strip(), 1 if enabled else 0, persona_name)
            )
            conn.commit()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def delete_persona(persona_name: str) -> dict:
    """ペルソナを削除する"""
    with get_connection() as conn:
        conn.execute("DELETE FROM persona_settings WHERE persona_name=?", (persona_name,))
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


def delete_council_session(session_id: int) -> dict:
    """相談セッションを削除する（採用回答もCASCADE削除）"""
    with get_connection() as conn:
        conn.execute("DELETE FROM council_sessions WHERE id=?", (session_id,))
        conn.commit()
    return {"status": "ok"}


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
    """採用した回答を保存する（同一セッション・同一ペルソナの重複は無視）"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        # 既に同じペルソナの回答が登録されていれば追加しない
        exists = conn.execute(
            "SELECT id FROM council_adopted WHERE session_id=? AND persona_name=?",
            (session_id, persona_name)
        ).fetchone()
        if exists:
            return exists['id']
        cursor = conn.execute(
            "INSERT INTO council_adopted (session_id, persona_name, answer, created_at) VALUES (?, ?, ?, ?)",
            (session_id, persona_name, answer.strip(), now)
        )
        conn.commit()
    print(f"[database] 採用回答保存: session={session_id} persona={persona_name}")
    return cursor.lastrowid


def get_council_sessions(category_id: int = None, keyword: str = "", date_from: str = "", date_to: str = "", limit: int = 100) -> list[dict]:
    """相談履歴を検索・フィルターして返す"""
    with get_connection() as conn:
        query  = """
            SELECT cs.id, cs.question, cs.category_id, cs.final_decision, cs.created_at,
                   c.name AS category_name
            FROM council_sessions cs
            LEFT JOIN categories c ON c.id = cs.category_id
            WHERE 1=1
        """
        params = []
        if category_id:
            query += " AND cs.category_id = ?"
            params.append(category_id)
        if keyword:
            query += " AND (cs.question LIKE ? OR cs.final_decision LIKE ?)"
            params.extend([f"%{keyword}%", f"%{keyword}%"])
        if date_from:
            query += " AND cs.created_at >= ?"
            params.append(date_from)
        if date_to:
            query += " AND cs.created_at <= ?"
            params.append(date_to + " 23:59:59")
        query += f" ORDER BY cs.created_at DESC LIMIT {limit}"

        sessions = conn.execute(query, params).fetchall()
        result   = []
        for s in sessions:
            adopted = conn.execute(
                "SELECT id, persona_name, answer, rating FROM council_adopted WHERE session_id=? ORDER BY rating DESC, created_at",
                (s['id'],)
            ).fetchall()
            d = dict(s)
            d['adopted'] = [dict(a) for a in adopted]
            result.append(d)
    return result


def update_adopted_rating(adopted_id: int, rating: int) -> dict:
    """採用回答の評価（★1〜5）を更新する"""
    with get_connection() as conn:
        conn.execute(
            "UPDATE council_adopted SET rating=? WHERE id=?",
            (max(0, min(5, rating)), adopted_id)
        )
        conn.commit()
    return {"status": "ok"}


def get_highly_rated_answers(persona_name: str, limit: int = 3) -> list[dict]:
    """指定ペルソナの高評価回答（★3以上）を返す"""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT ca.id, ca.answer, ca.rating, cs.question
               FROM council_adopted ca
               JOIN council_sessions cs ON cs.id = ca.session_id
               WHERE ca.persona_name = ? AND ca.rating >= 3
               ORDER BY ca.rating DESC, ca.created_at DESC
               LIMIT ?""",
            (persona_name, limit)
        ).fetchall()
    return [dict(r) for r in rows]


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


def get_context_for_categories(category_ids: list) -> dict:
    """複数カテゴリに紐づくコンテキストデータを収集する"""
    if not category_ids:
        return {"recordings": [], "memos": [], "files": [], "sessions": []}
    if len(category_ids) == 1:
        return get_context_for_category(category_ids[0])

    placeholders = ",".join("?" * len(category_ids))
    with get_connection() as conn:
        recordings = conn.execute(
            f"SELECT id, title, ai_summary, category_id FROM recordings WHERE category_id IN ({placeholders}) AND ai_summary != '' ORDER BY created_at DESC LIMIT 20",
            category_ids
        ).fetchall()
        memos = conn.execute(
            f"SELECT id, title, body, category_id FROM vault_memos WHERE category_id IN ({placeholders}) ORDER BY created_at DESC LIMIT 20",
            category_ids
        ).fetchall()
        files = conn.execute(
            f"SELECT id, original_name, summary, category_id FROM vault_files WHERE category_id IN ({placeholders}) AND summary != '' ORDER BY created_at DESC LIMIT 20",
            category_ids
        ).fetchall()
        sessions = conn.execute(
            f"""SELECT cs.question, cs.final_decision, ca.persona_name, ca.answer, cs.category_id
               FROM council_sessions cs
               LEFT JOIN council_adopted ca ON ca.session_id = cs.id
               WHERE cs.category_id IN ({placeholders})
               ORDER BY cs.created_at DESC LIMIT 10""",
            category_ids
        ).fetchall()

    return {
        "recordings": [dict(r) for r in recordings],
        "memos":      [dict(m) for m in memos],
        "files":      [dict(f) for f in files],
        "sessions":   [dict(s) for s in sessions],
    }
