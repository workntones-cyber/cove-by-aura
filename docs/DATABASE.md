# データベース設計

## 概要

AURAはSQLite3を使用してローカルにデータを保存します。データベースファイルは `app/aura.db` に保存されます。

---

## テーブル一覧

| テーブル名 | 概要 |
|---|---|
| recordings | 録音データのメタデータ・処理結果を管理 |

---

## recordings テーブル

### カラム定義

| カラム名 | 型 | デフォルト | 説明 |
|---|---|---|---|
| id | INTEGER | AUTOINCREMENT | レコードID（主キー） |
| title | TEXT | '無題' | ユーザーが入力した録音タイトル |
| memo | TEXT | '' | ユーザーが入力した概要メモ |
| wav_file | TEXT | '' | WAVファイル名（uploads/配下） |
| transcript | TEXT | '' | 文字起こし結果（生テキスト） |
| transcript_status | TEXT | 'pending' | 文字起こし処理状態 |
| cleaned_transcript | TEXT | '' | クリーニング済みテキスト |
| cleaning_status | TEXT | 'pending' | クリーニング処理状態 |
| ai_summary | TEXT | '' | AI要約結果 |
| summary_status | TEXT | 'pending' | 要約処理状態 |
| created_at | TEXT | CURRENT_TIMESTAMP | レコード作成日時（ISO 8601） |
| updated_at | TEXT | CURRENT_TIMESTAMP | レコード更新日時（ISO 8601） |

### DDL

```sql
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
    created_at          TEXT    NOT NULL,
    updated_at          TEXT    NOT NULL
);
```

---

## ステータス値定義

### transcript_status（文字起こし状態）

| 値 | 説明 | 画面表示 |
|---|---|---|
| `pending` | 未実行または処理待ち | 🔄 文字起こしボタンを表示 |
| `done` | 文字起こし完了 | 文字起こしタブに結果を表示 |
| `error` | 文字起こし失敗 | 🔄 文字起こしボタンを表示 |

### cleaning_status（クリーニング状態）

| 値 | 説明 | 画面表示 |
|---|---|---|
| `pending` | 未実行または処理待ち | クリーニングタブなし |
| `done` | クリーニング完了 | 🧹 クリーニング済みタブに結果を表示 |
| `error` | クリーニング失敗 | クリーニングタブなし |

### summary_status（要約状態）

| 値 | 説明 | 画面表示 |
|---|---|---|
| `pending` | 未実行または処理待ち | 🔄 再要約ボタンを表示 |
| `done` | 要約完了 | ✨ AI要約タブに結果を表示 |
| `error` | 要約失敗 | 🔄 再要約ボタンを表示 |

---

## ステータス遷移図

```mermaid
stateDiagram-v2
    [*] --> pending : レコード作成時

    state "transcript_status" as ts {
        pending --> done : 文字起こし成功
        pending --> error : 文字起こし失敗
        error --> done : 再実行成功
        done --> done : 再実行成功
    }

    state "cleaning_status" as cs {
        pending --> done : クリーニング成功
        pending --> error : クリーニング失敗
        error --> done : 再実行成功
        done --> done : 再実行成功
    }

    state "summary_status" as ss {
        pending --> done : 要約成功
        pending --> error : 要約失敗
        error --> done : 再実行成功
        done --> done : 再実行成功
    }
```

---

## データ操作関数（database.py）

| 関数名 | 説明 |
|---|---|
| `init_db()` | DB初期化・マイグレーション実行 |
| `create_recording(wav_file, title, memo)` | 録音レコード新規作成 |
| `get_recording(record_id)` | IDでレコードを取得 |
| `get_all_recordings()` | 全レコードを降順で取得 |
| `update_transcript_and_summary(id, transcript, ai_summary)` | 文字起こし・要約を保存 |
| `update_cleaned_transcript(id, cleaned_transcript)` | クリーニング結果を保存 |
| `update_title_and_memo(id, title, memo)` | タイトル・メモを更新 |
| `delete_recording(id)` | レコードとWAVファイルを削除 |
| `delete_all_recordings()` | 全レコードを削除 |

---

## マイグレーション

アプリ起動時に `init_db()` が自動実行され、既存DBに不足カラムを追加します。

```python
# 既存DBへのマイグレーション（カラムがなければ追加）
for col, default in [
    ("transcript_status",  "'pending'"),
    ("cleaned_transcript", "''"),
    ("cleaning_status",    "'pending'"),
    ("summary_status",     "'pending'"),
]:
    try:
        conn.execute(f"ALTER TABLE recordings ADD COLUMN {col} TEXT NOT NULL DEFAULT {default}")
    except Exception:
        pass  # すでに存在する場合はスキップ
```
