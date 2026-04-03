# COVE by AURA　
Collective Opinion & Vision Engine

**意思決定支援ツール**

すべての処理がローカルPC上で完結するため、機密性の高い情報を外部に送信することなく利用できます。(ローカルAI設定時)
状況に応じて、クラウドAI(GPT-4o,Gemini,Cloude,Llama)に変更することが可能です。

---

## 主な機能

| 画面 | 機能 |
|---|---|
| 🎙️ **録音** | 会議・打ち合わせを録音し、AIが自動で文字起こし・クリーニング・要約 |
| 🗄️ **保管庫** | テキストメモ・ファイル・Webデータ・録音データをカテゴリで一元管理 |
| 🔍 **照会室** | アーカイバーが保管データから必要な情報を抽出・整理（会話継続対応） |
| 💬 **相談室** | 8人のAIペルソナが多角的な視点から意見を提示（連続相談対応） |
| ⚙️ **設定** | ペルソナのカスタマイズ・カテゴリ管理 |

---

## システム要件

### Windows
| 項目 | 最小要件 | 推奨 |
|---|---|---|
| OS | Windows 10 64bit | Windows 11 |
| RAM | 16GB | 32GB以上 |
| VRAM | 8GB | 16GB以上（NVIDIA GPU） |
| ストレージ | 30GB以上 | 50GB以上 |

### Mac
| 項目 | 最小要件 | 推奨 |
|---|---|---|
| チップ | Apple Silicon（M1以降） | M5 Pro以降 |
| RAM | 16GB | 36GB以上 |
| ストレージ | 30GB以上 | 50GB以上 |
| OS | macOS 13 Ventura以降 | 最新版 |

---

## セットアップ

### 1. uv のインストール

**Windows（PowerShell）**
```powershell
winget install --id=astral-sh.uv -e
```

**Mac（Terminal）**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Ollama のインストール

**Windows**：https://ollama.com/download からインストーラーをダウンロード

**Mac**
```bash
brew install ollama
```

### 3. AIモデルのダウンロード（約17GB）

```bash
ollama pull gemma3:27b
```

> ダウンロードには30分〜2時間程度かかります。完了するまでウィンドウを閉じないでください。

### 4. ffmpeg のインストール（トリミング機能用・任意）

**Windows**
```powershell
winget install ffmpeg
```

**Mac**
```bash
brew install ffmpeg
```

### 5. COVE のセットアップ

```bash
cd cove-by-aura
uv sync
```

---

## 起動・終了

**起動**
```bash
uv run python main.py
```

起動後、ブラウザが自動で開きます。開かない場合は http://127.0.0.1:5001 にアクセスしてください。

**終了**：画面右上の「⏻ 終了」ボタンをクリック

> ⚠️ ブラウザのタブを閉じるだけではCOVEは終了しません。

---

## ナビゲーション構成

```
🎙️ 録音  |  🗄️ 保管庫  |  🔍 照会室  |  💬 相談室  |  ⚙️ 設定  |  ❓
```

---

## ペルソナ一覧

### 相談室（8ペルソナ）
| ペルソナ | 視点 | 得意なこと |
|---|---|---|
| ▶ 戦略家 | 攻撃的・勝ちにいく | 勝ち筋・具体的な行動方針 |
| ⚠ リスク管理者 | 保守的・問題指摘 | 落とし穴の発見・最悪シナリオ |
| 📊 アナリスト | データ・客観的分析 | 構造的判定・根拠の整理 |
| 💡 クリエイター | 発想力・斬新アイデア | 誰もやっていないアイデア |
| ⚖ 法務・コンプラ | 規則・法的観点 | 法的リスク・適法な代替案 |
| 👤 ユーザー視点 | 現場・顧客目線 | 第一印象・離脱ポイント |
| 🔥 クレーマー | 批判・欠点指摘 | 致命的欠陥・矛盾の発見 |
| 📣 マーケッター | 市場・ブランド戦略 | 売れる/売れない判定・差別化 |

### 照会室専用
| ペルソナ | 役割 |
|---|---|
| 🗂 アーカイバー | 保管データから事実・記録のみを抽出・整理。意見は言わず、矛盾・見落とし発見時のみ一言添える |

---

## ファイル構成

```
cove-by-aura/
├── main.py                    Flask（全APIエンドポイント）
├── pyproject.toml             依存パッケージ定義
├── uv.lock                    依存関係ロックファイル
├── cove.spec                  PyInstallerビルド設定
├── cove.ico                   アプリアイコン（Windows）
├── cove.iconset/              アプリアイコン素材（Mac .icns 変換用）
├── .env                       環境変数（APIキー等）※gitignore
├── env.example                .env テンプレート
├── app/
│   ├── database.py            SQLite操作・スキーマ定義
│   ├── cove.db                データベース ※gitignore
│   └── services/
│       ├── transcriber.py     文字起こし・クリーニング・要約
│       └── recorder.py        音声録音
├── app/templates/
│   ├── index.html             録音画面
│   ├── vault.html             保管庫
│   ├── inquiry.html           照会室
│   ├── council.html           相談室
│   ├── settings.html          設定画面
│   └── help.html              取扱説明書
├── app/static/
│   ├── css/style.css          共通スタイル
│   ├── js/recorder.js         録音画面JS
│   ├── js/settings.js         設定画面JS
│   ├── cove.ico               ファビコン
│   └── img/personas/          ペルソナアイコン画像
├── uploads/                   録音WAVファイル ※gitignore
└── vault/                     保管庫ファイル ※gitignore
```

---

## 環境変数（.env）

```env
# AIモード: business（Ollama）/ personal（Groq）
AI_MODE=business

# Groq APIキー（personalモード時のみ必要）
GROQ_API_KEY=

# Ollamaモデル名
OLLAMA_MODEL=gemma3:27b
```

`env.example` をコピーして `.env` を作成してください。

---

## PyInstallerでのビルド

```bash
uv run pyinstaller cove.spec
```

**Mac用アイコン（.icns）の事前準備**
```bash
iconutil -c icns cove.iconset
# → cove.icns が生成される（cove.spec の icon= を cove.icns に変更）
```

ビルド成果物は `dist/COVE/` に生成されます。

---

## 技術スタック

| 項目 | 内容 |
|---|---|
| バックエンド | Python 3.12 / Flask |
| パッケージ管理 | uv |
| データベース | SQLite3 |
| ローカルLLM | Ollama（gemma3:27b推奨） |
| 文字起こし | faster-whisper |
| 音声処理 | sounddevice / soundfile |
| フロントエンド | HTML / CSS / Vanilla JS（SSEストリーミング） |

---

## プライバシー・セキュリティ

- すべての処理はPC上でローカルに完結
- 録音・メモ・相談内容は外部サーバーに送信されません
- インターネット通信が発生するのは初回セットアップ時と保管庫のWebデータ取得のみ

詳細は [SECURITY.md](SECURITY.md) を参照してください。

---

## ライセンス

[LICENSE](LICENSE) を参照してください。

### 使用しているOSS

| ソフトウェア | ライセンス | 用途 |
|---|---|---|
| Flask | BSD License | Webサーバー |
| faster-whisper | MIT License | 音声文字起こし |
| Ollama | MIT License | ローカルLLM実行 |
| SQLite | Public Domain | データベース |
| ffmpeg | LGPL / GPL | 音声トリミング |

---

## 免責事項

COVEが提供する情報はAIによる参考意見です。法的・財務的・医療的判断など重要な意思決定は、必ず専門家の意見を確認してください。AIの回答は誤りを含む場合があります。最終判断は必ず人間が行ってください。
