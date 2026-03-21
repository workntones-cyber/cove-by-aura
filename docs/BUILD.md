# ビルド・開発者向け情報

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
git clone https://github.com/workntones-cyber/aura.git
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