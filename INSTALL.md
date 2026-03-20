# インストール手順

## 📦 パッケージ版（.exe）を使う場合（一般ユーザー向け）

Python や開発環境は不要です。以下の手順だけで使い始められます。

1. `AURA.exe` をダウンロードして任意のフォルダに置く
2. **ビジネス用モードを使う場合は、先に Ollama をインストールしてください**（下記参照）
3. `AURA.exe` をダブルクリックして起動
4. ブラウザが自動で開くので、設定画面でAPIキーを入力する

> ⚠️ Norton などのセキュリティソフトが警告を出す場合があります。「セキュリティソフトの警告について」のセクションを参照してください。

---

## 🤖 Ollama のインストール（ビジネス用モードに必須）

ビジネス用モードでは、要約処理に **Ollama**（ローカルLLM）を使用します。音声データを外部に送信せず、PC上で完全ローカル処理するために必要です。

> 個人用モードのみ使用する場合は不要です。

### Step 1：Ollamaをインストール

**Windows の場合：**

1. スタートメニューで「PowerShell」を検索して起動します
2. ブラウザで [https://ollama.com/download](https://ollama.com/download) を開きます
3. 「Download for Windows」をクリックしてインストーラーをダウンロードします
4. ダウンロードした `OllamaSetup.exe` をダブルクリックして実行します
5. インストール完了後、PowerShellで確認します：

```powershell
ollama --version
```

`ollama version is x.x.x` と表示されれば成功です。

### Step 2：言語モデルをダウンロード（約5GB）

```powershell
ollama pull llama3.1:8b
```

> ⚠️ 初回のみダウンロードが発生します。通信環境によっては数分〜数十分かかります。

動作確認：
```powershell
ollama run llama3.1:8b "こんにちは"
```

日本語で返答が返ってきたら準備完了です。

### Step 3：Ollamaを起動した状態でAURAを使う

OllamaはPC起動時に自動起動します。タスクトレイにアイコンが表示されていれば起動中です。もし起動していない場合は以下を実行してください：

```powershell
ollama serve
```

---

## 🛠️ ソースから起動する場合（開発者向け）

### 事前準備

#### Python 3.11 以上のインストール

[https://www.python.org/downloads/](https://www.python.org/downloads/) から最新版をダウンロードしてインストールします。

> ⚠️ Windowsの場合：インストール時に「**Add Python to PATH**」にチェックを入れてください。

インストール確認：
```bash
python --version
```

#### uv のインストール

**Windows（PowerShell）：**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Mac / Linux：**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

インストール確認：
```bash
uv --version
```

---

### 1. リポジトリをクローン

```bash
git clone https://github.com/workntones-cyber/aura.git
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
- **Windows：** [http://127.0.0.1:5001](http://127.0.0.1:5001)
- **Mac：** [http://127.0.0.1:5001](http://127.0.0.1:5001)

---