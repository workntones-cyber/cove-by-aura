# AURA
**Audio Understanding & Recording Assistant**

音声を録音し、AIが自動で文字起こし・要約するデスクトップアプリです。

---

## 概要・利用用途

AURAは、会議・打ち合わせ・インタビューなどの音声を録音し、AIが自動で文字起こしと要約を行うツールです。録音後すぐに内容を把握でき、議事録作成の手間を大幅に削減します。

**こんな場面に最適です：**
- 会議室にノートPCを持ち込んで録音 → 自動で議事録を生成
- 1on1・面談の記録
- 講演・セミナーのメモ作成
- ひとりでのアイデアメモ・口述筆記

> **注意：** AURAはPCのマイク入力またはシステム音声を録音します。オンライン会議（Zoom・Google Meet等）の音声を録音するには、設定画面で「システム音声」モードに切り替えてください。Macの場合は別途BlackHoleのインストールが必要です。

---

## 動作環境・必要要件

### 共通
| 項目 | 要件 |
|---|---|
| Python | 3.11 以上 |
| パッケージ管理 | [uv](https://docs.astral.sh/uv/) |
| ブラウザ | Chrome / Edge / Safari（最新版推奨） |
| マイク | PC内蔵マイク または 外付けマイク |

### Windows
| 項目 | 要件 |
|---|---|
| OS | Windows 10 / 11 |
| ビジネス用モード（faster-whisper） | GPU VRAM 8GB以上推奨（CPUでも動作可・処理に時間がかかる場合あり） |

### Mac
| 項目 | 要件 |
|---|---|
| OS | macOS 12 以上 |
| 対応チップ | Apple Silicon（M1 / M2 / M3）推奨 |
| ビジネス用モード（faster-whisper） | Apple Silicon Mac のみ対応（Intel Mac は個人用モードのみ） |
| ポート | 5001（macOS 12以降はポート5000がシステムに占有されるため） |

---

## AIモード

AURAには2つのAIモードがあります。設定画面から切り替えられます。

### 👤 個人用モード（Groq API）

クラウド上のAIを使って文字起こし・要約を行います。

- **文字起こし：** Groq Whisper（`whisper-large-v3-turbo`）
- **要約：** Groq LLaMA（`llama-3.3-70b-versatile`）
- **必要なもの：** Groq APIキー（無料で取得可能）
- **特徴：** セットアップが簡単・高速・高精度

Groq APIキーの取得：[https://console.groq.com/keys](https://console.groq.com/keys)

### 🏢 ビジネス用モード（faster-whisper）

音声データを外部に送信せず、PC上で完全ローカル処理します。

- **文字起こし：** faster-whisper（`medium` モデル・約1.5GB）
- **要約：** Groq LLaMA（Groq APIキーがあれば使用）
- **必要なもの：** 初回起動時にモデルファイルを自動ダウンロード（約1.5GB）
- **特徴：** 機密情報・社内情報の録音に最適。音声データが外部に出ない

> **対応環境：** Windows（GPU/CPU）、Mac Apple Silicon（CPU）

---

## 録音モード

設定画面から録音ソースを切り替えられます。

### 🎤 マイク入力（デフォルト）

PC内蔵マイクまたは外付けマイクで録音します。対面会議・インタビューに最適です。

> オンライン会議（Zoom・Meet等）の相手の音声は録音されません。

### 🖥️ システム音声（オンライン会議対応）

PCから出力されるすべての音声を録音します。オンライン会議の音声録音に最適です。

**Windows の場合：** 追加設定不要で利用できます。

**Mac の場合：** BlackHole のインストールが必要です。

#### Mac：BlackHole セットアップ手順

**Step 1. BlackHole 2ch をダウンロード・インストール**

[https://existential.audio/blackhole/](https://existential.audio/blackhole/) から **「BlackHole 2ch」** をダウンロードしてインストールします（16ch・64ch は不要）。

**Step 2. Mac を再起動**

インストール後、必ず再起動してください。

**Step 3. Audio MIDI設定で「複数出力装置」を作成**

1. Finder →「アプリケーション」→「ユーティリティ」→「Audio MIDI設定」を開く
2. 左下の「＋」→「複数出力装置を作成」
3. 「BlackHole 2ch」と使用中のスピーカーの両方にチェック

**Step 4. システム設定でサウンド出力を切り替え**

「システム設定」→「サウンド」→ 出力を「複数出力装置」に変更します。

> ⚠️ この設定後はキーボードでの音量調整が効かなくなります。事前に「システム設定」→「コントロールセンター」→「サウンド」→「メニューバーに表示：常に表示」に設定しておくと、メニューバーの🔊アイコンから音量調整できます。

**Step 5. AURA を再起動**

再起動後、AURAがBlackHoleを自動検出します。設定画面で「✅ BlackHole を検出しました」と表示されれば完了です。


---

## インストール手順

### 1. リポジトリをクローン

```bash
git clone https://github.com/yourusername/aura.git
cd aura
```

### 2. 依存パッケージをインストール

```bash
uv sync
```

### 3. 環境変数ファイルを作成

```bash
cp .env.example .env
```

`.env` を開いて Groq APIキーを設定します（個人用モードを使う場合）：

```
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxx
AI_MODE=personal
```

### 4. 起動

```bash
uv run python main.py
```

ブラウザで以下のURLを開いてください：
- **Windows：** [http://127.0.0.1:5000](http://127.0.0.1:5000)
- **Mac：** [http://127.0.0.1:5001](http://127.0.0.1:5001)

---

## 使い方

### 基本的な流れ

```
① 設定画面でAIモードとAPIキーを設定
      ↓
② 録音画面でタイトル・概要メモを入力（任意）
      ↓
③ 録音ボタンを押して録音開始
      ↓
④ 録音停止ボタンを押す
      ↓
⑤ 自動で文字起こし → AI要約が実行される
      ↓
⑥ 結果を確認・編集して保存
```

### 長時間録音について

録音は10分ごとに自動でチャンク分割されます。何時間でも録音可能です。
Groq APIの25MBファイルサイズ制限も自動で対応します。

### 過去の録音データ

録音画面下部のプルダウンから過去の録音データを参照できます。
文字起こし・要約の確認、タイトル・メモの編集、削除が可能です。

### データの保存場所

| データ | 保存場所 |
|---|---|
| 録音音声（WAV） | `uploads/` フォルダ |
| 文字起こし・要約 | `app/aura.db`（SQLite） |
| APIキー・設定 | `.env` ファイル |

---

## 配布用ビルド（PyInstaller）

Python環境なしで実行できる単一ファイルにビルドします。

```bash
# パッケージを追加
uv add pyinstaller

# ビルド
uv run pyinstaller aura.spec
```

ビルド完了後、`dist/AURA.exe`（Windows）または `dist/AURA`（Mac）が生成されます。

実行すると自動的にブラウザが開きます。
ブラウザが開かない場合は以下にアクセスしてください：
- **Windows：** [http://127.0.0.1:5000](http://127.0.0.1:5000)
- **Mac：** [http://127.0.0.1:5001](http://127.0.0.1:5001)

> **初回実行時の注意：** ビジネス用モードを使う場合、`dist/` フォルダと同じ場所に `.env` ファイルを作成してAPIキーを設定してください。

---

## 開発者向け情報

### 技術スタック

| 項目 | 採用技術 |
|---|---|
| 言語 / フレームワーク | Python 3.11+ / Flask |
| パッケージ管理 | uv |
| 録音（マイク） | sounddevice（16000Hz / モノラル / int16） |
| 録音（システム音声・Windows） | pyaudiowpatch（WASAPI ループバック） |
| 録音（システム音声・Mac） | sounddevice + BlackHole |
| 個人用AI | Groq API（Whisper + LLaMA） |
| ビジネス用AI | faster-whisper（ローカル） |
| データベース | SQLite |
| パッケージング | PyInstaller |

### ディレクトリ構成

```
aura/
├── main.py                    # Flaskアプリ本体・APIエンドポイント
├── aura.spec                  # PyInstallerビルド設定
├── .env                       # APIキー・設定（gitignore済み）
├── .env.example               # .envのテンプレート
├── pyproject.toml
├── app/
│   ├── database.py            # SQLite操作
│   ├── services/
│   │   ├── recorder.py        # 録音・チャンク分割
│   │   └── transcriber.py     # 文字起こし・要約（Groq / faster-whisper）
│   ├── templates/
│   │   ├── index.html         # 録音画面
│   │   └── settings.html      # 設定画面
│   └── static/
│       ├── css/style.css
│       └── js/
│           ├── recorder.js
│           └── settings.js
└── uploads/                   # 録音WAVファイル（gitignore済み）
```

### 開発環境のセットアップ

```bash
git clone https://github.com/yourusername/aura.git
cd aura
uv sync
cp .env.example .env
uv run python main.py   # debug=True で起動
```

### Windows → Mac の開発フロー

```bash
# Windows で実装
git add .
git commit -m "feat: ..."
git push

# Mac で確認
git pull
uv sync
uv run python main.py
```

### ブランチ運用

| ブランチ | 用途 |
|---|---|
| `main` | 安定版 |
| `feature/*` | 機能追加 |

---

## セキュリティソフトの警告について

### Norton / Windows Defender などのウイルス対策ソフト

`AURA.exe` を初回実行した際に「疑わしいファイルを検出しました」などの警告が表示される場合があります。

これは **誤検知（False Positive）** です。AURAは悪意のある処理を一切行いません。

**なぜ警告が出るのか：**
- PyInstaller でパッケージ化した `.exe` ファイルは、ウイルス対策ソフトが「未知のプログラム」として検出することがあります
- マイクへのアクセスやネットワーク通信（Groq API）を行うため、疑わしい挙動として検知される場合があります
- AURAはオープンソースであり、ソースコードはすべて公開されています

**対処方法：**

Norton の場合：
1. 警告画面で「詳細を表示」→「信頼する」または「許可する」を選択
2. または Norton の「ファイルの除外設定」に `AURA.exe` を追加

Windows Defender の場合：
1. 「詳細情報」→「実行」を選択
2. または「ウイルスと脅威の防止」→「除外の追加」に `AURA.exe` を追加

> 心配な場合はソースコードをご確認いただくか、`uv run python main.py` で直接起動することもできます。


---

## ライセンス

MIT License
