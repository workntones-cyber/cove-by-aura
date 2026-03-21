# API エンドポイント仕様

## 概要

すべてのAPIはFlask（`main.py`）で定義されています。レスポンスはJSON形式です。ベースURLは `http://127.0.0.1:5001` です。

---

## 画面

| メソッド | エンドポイント | 説明 |
|---|---|---|
| GET | `/` | 録音画面（index.html）を返却 |
| GET | `/settings` | 設定画面（settings.html）を返却 |
| GET | `/favicon.ico` | ファビコンを返却 |

---

## 録音API

### POST /api/record/start
録音を開始します。

**レスポンス**
```json
{ "status": "started", "session_id": "aura_20260101_120000" }
```

### POST /api/record/stop
録音を停止してWAVファイルを保存します。

**レスポンス**
```json
{ "status": "stopped", "record_id": 1, "duration": 30.5 }
```

### POST /api/transcribe
文字起こし・クリーニング・要約を実行します。

**リクエスト**
```json
{ "record_id": 1, "extra_prompt": "技術用語を優先して記載してください" }
```

**レスポンス**
```json
{
  "status": "done",
  "transcript": "文字起こし結果...",
  "cleaned_transcript": "クリーニング済みテキスト...",
  "ai_summary": "要約テキスト..."
}
```

### POST /api/clean
クリーニングのみ再実行します。

**リクエスト**
```json
{ "record_id": 1 }
```

**レスポンス**
```json
{ "status": "done", "cleaned_transcript": "クリーニング済みテキスト..." }
```

### POST /api/summarize
要約のみ再実行します。

**リクエスト**
```json
{ "record_id": 1, "extra_prompt": "箇条書きで簡潔にまとめてください" }
```

**レスポンス**
```json
{ "status": "done", "ai_summary": "要約テキスト..." }
```

---

## 録音データ管理API

### GET /api/recordings
全録音データを降順で返します。

**レスポンス**
```json
[
  {
    "id": 1,
    "title": "週次定例会議",
    "memo": "Q1売上について",
    "wav_file": "aura_20260101_120000.wav",
    "transcript": "文字起こし結果...",
    "transcript_status": "done",
    "cleaned_transcript": "クリーニング済み...",
    "cleaning_status": "done",
    "ai_summary": "要約...",
    "summary_status": "done",
    "created_at": "2026-01-01 12:00:00",
    "updated_at": "2026-01-01 12:05:00"
  }
]
```

### PATCH /api/recordings/:id
タイトル・メモを更新します。

**リクエスト**
```json
{ "title": "週次定例会議", "memo": "Q1売上について" }
```

**レスポンス**
```json
{ "status": "updated" }
```

### DELETE /api/recordings/:id
録音データとWAVファイルを削除します。

**レスポンス**
```json
{ "status": "deleted" }
```

### DELETE /api/recordings/all
全録音データを削除します。

**レスポンス**
```json
{ "status": "deleted", "count": 5 }
```

---

## 設定API

### GET /api/settings
現在の設定を返します。

**レスポンス**
```json
{
  "ai_mode": "business",
  "groq_api_key": "****xxxx",
  "has_groq_key": true,
  "recording_source": "system",
  "recording_device_id": "",
  "ollama_model": "gemma3:27b"
}
```

### POST /api/settings
設定を保存します。ビジネス用モード選択時はモデルプリロードを開始します。

**リクエスト**
```json
{
  "ai_mode": "business",
  "groq_api_key": "gsk_xxxx",
  "recording_source": "system",
  "recording_device_id": "",
  "ollama_model": "gemma3:27b"
}
```

**レスポンス**
```json
{ "status": "saved" }
```

---

## モデル・Ollama API

### GET /api/model/status
faster-whisperモデルのロード状態を返します。

**レスポンス**
```json
{ "status": "idle|loading|ready|error", "error": null, "model": "medium" }
```

### GET /api/ollama/status
Ollamaの起動状態を返します。

**レスポンス**
```json
{ "status": "running|not_running" }
```

### GET /api/ollama/models
Ollamaにインストール済みのモデル一覧を返します。

**レスポンス**
```json
{ "status": "ok", "models": ["llama3.1:8b", "gemma3:27b"] }
```

---

## その他API

### GET /api/devices
利用可能な録音デバイス一覧を返します。

**レスポンス**
```json
[
  { "id": 0, "name": "マイク（内蔵）" },
  { "id": 1, "name": "BlackHole 2ch" }
]
```

### GET /audio/:filename
WAVファイルをストリーミング配信します。

### POST /api/shutdown
AURAとOllamaを終了します。

**レスポンス**
```json
{ "status": "ok" }
```

---

## エラーレスポンス

すべてのAPIはエラー時に以下の形式で返します。

```json
{ "status": "error", "message": "エラーの詳細メッセージ" }
```

| HTTPステータス | 意味 |
|---|---|
| 400 | リクエストパラメータ不足・不正 |
| 404 | レコードが見つからない |
| 500 | サーバー内部エラー |
