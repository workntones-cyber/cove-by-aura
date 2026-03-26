# COVE by AURA

> 完全ローカル・完全秘匿の AI 意思決定支援ツール

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.x-lightgrey.svg)](https://flask.palletsprojects.com/)
[![Ollama](https://img.shields.io/badge/Ollama-required-orange.svg)](https://ollama.com/)
[![License](https://img.shields.io/badge/License-Private-red.svg)]()

---

## 概要

COVE は、経営者・管理職向けの **完全ローカル動作** する AI 意思決定支援ツールです。  
録音・文字起こし・保管庫・複数ペルソナによる多角的相談を、インターネット接続なしで完結させます。

**秘匿性が最大の特徴です。** 会議録音・経営判断・個人情報は一切クラウドに送信されません。

### 主な機能

| 機能 | 説明 |
|---|---|
| 🎙️ **録音** | マイク・システム音声の録音、文字起こし、AI 要約 |
| 🗄️ **保管庫** | テキストメモ・ファイル・Web データ・録音データを一元管理 |
| 💬 **相談室** | 8 種のペルソナが多角的な視点で意思決定を支援 |
| ⚙️ **設定** | ペルソナ・カテゴリ・AI モデルのカスタマイズ |

---

## 動作環境

| 項目 | 要件 |
|---|---|
| OS | Windows 10/11、macOS 13 (Ventura) 以降 |
| Python | 3.12 以上 |
| RAM | 16GB 以上推奨（gemma3:27b 使用時は 24GB 以上） |
| VRAM / 統合メモリ | 8GB 以上（16GB 以上推奨） |
| ストレージ | 30GB 以上の空き容量（モデルファイル含む） |

---

## セットアップ

### 1. 必要なツールのインストール

#### Python / uv

```bash
# uv のインストール（Windows）
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# uv のインストール（Mac）
curl -LsSf https://astral.sh/uv/install.sh | sh
```

#### Ollama

[https://ollama.com/download](https://ollama.com/download) からインストーラーをダウンロードして実行してください。

#### ffmpeg

```bash
# Windows（winget）
winget install ffmpeg

# Mac（Homebrew）
brew install ffmpeg
```

---

### 2. リポジトリのクローン

```bash
git clone https://github.com/workntones-cyber/cove-by-aura.git
cd cove-by-aura
```

---

### 3. AI モデルのダウンロード

```bash
# 推奨モデル（約17GB・ダウンロードに30分〜1時間程度）
ollama pull gemma3:27b

# VRAM が 8GB の場合はこちら
ollama pull gemma3:12b
```

---

### 4. 依存パッケージのインストール

```bash
uv sync
```

---

### 5. 起動

```bash
uv run python main.py
```

ブラウザで [http://127.0.0.1:5001](http://127.0.0.1:5001) にアクセスしてください。  
起動後、設定画面で **AI モード → ビジネス用** を選択してください。

---

## ディレクトリ構成

```
cove-by-aura/
├── main.py                         # Flask アプリ・全 API エンドポイント
├── app/
│   ├── database.py                 # DB スキーマ・CRUD 関数
│   ├── cove.db                     # SQLite データベース（自動生成）
│   ├── services/
│   │   ├── transcriber.py          # 文字起こし・クリーニング・要約
│   │   └── recorder.py             # 録音デバイス管理
│   ├── templates/
│   │   ├── index.html              # 録音画面
│   │   ├── vault.html              # 保管庫
│   │   ├── council.html            # 相談室
│   │   └── settings.html          # 設定画面
│   └── static/
│       ├── css/style.css
│       ├── js/
│       │   ├── recorder.js
│       │   └── settings.js
│       └── img/personas/           # ペルソナアイコン画像
├── uploads/                        # 録音 WAV ファイル（自動生成）
├── .env                            # 環境設定（自動生成）
└── README.md
```

---

## 設定・カスタマイズ

### AI モードの切り替え

設定画面（⚙️）→ AI モードから切り替えられます。

| モード | 説明 |
|---|---|
| **ビジネス用** | 完全ローカル（Ollama）。インターネット不要。秘匿性最大。 |
| 個人用 | Groq API を使用（API キー必要）。高速だがクラウド送信あり。 |

### Ollama モデルの変更

設定画面 → Ollama モデル設定 からモデルを切り替えられます。

| モデル | VRAM 目安 | 特徴 |
|---|---|---|
| `gemma3:27b` | 16GB〜 | **推奨**・高精度 |
| `gemma3:12b` | 8GB〜 | 軽量・高速 |
| `llama3.1:8b` | 6GB〜 | 最軽量 |

### ペルソナのカスタマイズ

設定画面 → ペルソナ管理 から 8 種のペルソナを追加・編集・削除できます。  
システムプロンプトを書き換えることで、業界特化型のペルソナを作成できます。

---

## データベース構成

```
categories        カテゴリ管理
recordings        録音データ（文字起こし・要約含む）
vault_memos       テキストメモ
vault_files       アップロードファイル
persona_settings  ペルソナ定義・システムプロンプト
council_sessions  相談履歴
council_adopted   採用回答・★評価
```

---

## プライバシー・セキュリティ

- **ビジネス用モードでは、すべての処理がローカルで完結します**
- 音声データ・テキスト・相談内容は外部サーバーに一切送信されません
- データは `app/cove.db`（SQLite）と `uploads/`（WAV ファイル）にのみ保存されます
- Ollama は `127.0.0.1:11434` でローカル起動します

---

## トラブルシューティング

### Ollama が起動しない

```bash
# Ollama の状態確認
ollama list

# 手動起動
ollama serve
```

### 文字起こしが失敗する

- Ollama が起動しているか確認してください
- `faster-whisper` のインストールを確認してください

```bash
uv add faster-whisper
```

### ffmpeg が見つからない

トリミング機能を使用するには ffmpeg が必要です。

```bash
# Windows
winget install ffmpeg

# Mac
brew install ffmpeg
```

PowerShell / ターミナルを再起動後に再試行してください。

### ポート 5001 が使用中

```bash
# Windows
netstat -ano | findstr :5001

# Mac / Linux
lsof -i :5001
```

---

## 技術スタック

| カテゴリ | 技術 |
|---|---|
| バックエンド | Python 3.12 / Flask |
| データベース | SQLite |
| AI 推論（ローカル） | Ollama（llama.cpp ベース） |
| 文字起こし | faster-whisper |
| フロントエンド | HTML / CSS / Vanilla JS |
| 音声処理 | Web Audio API / ffmpeg |
| パッケージ管理 | uv |

---

## ライセンス

Private - All Rights Reserved  
© 2026 AURA / workntones-cyber
