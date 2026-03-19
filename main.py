import os
import sys
import threading
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory

from app.database import (
    create_recording,
    delete_recording,
    get_all_recordings,
    get_recording,
    init_db,
    update_title_and_memo,
    update_transcript_and_summary,
)
from app.services.recorder import delete_recording as delete_wav
from app.services.recorder import get_status, list_recordings, start, stop

# ── PyInstaller対応：リソースパスの解決 ──────────────
# --onefile で固めた場合、リソースは一時展開ディレクトリに置かれる
# 通常実行時は main.py のある場所をベースにする
if getattr(sys, "frozen", False):
    # PyInstallerで固めた実行ファイルとして起動している
    BASE_DIR = Path(sys.executable).resolve().parent
    RESOURCE_DIR = Path(sys._MEIPASS)  # 一時展開ディレクトリ
else:
    # 通常のPython実行
    BASE_DIR     = Path(__file__).resolve().parent
    RESOURCE_DIR = BASE_DIR

app = Flask(
    __name__,
    template_folder=str(RESOURCE_DIR / "app" / "templates"),
    static_folder=str(RESOURCE_DIR / "app" / "static"),
)

# ── 起動時にDBを初期化 ────────────────────────────
init_db()


# ══════════════════════════════════════════════════
#  ページルーティング
# ══════════════════════════════════════════════════


@app.route("/api/shutdown", methods=["POST"])
def shutdown():
    """AURAを終了する"""
    import threading
    def _shutdown():
        import time, os, signal, subprocess
        time.sleep(0.3)  # レスポンスを返してから終了
        print("[main] シャットダウン要求を受信しました")
        # AURAが起動したOllamaを停止
        try:
            subprocess.run(["taskkill", "/F", "/IM", "ollama.exe"],
                         capture_output=True)
            print("[main] Ollamaを停止しました")
        except Exception as e:
            print(f"[main] Ollama停止エラー: {e}")
        os.kill(os.getpid(), signal.SIGTERM)
    threading.Thread(target=_shutdown, daemon=True).start()
    return jsonify({"status": "ok"}), 200

@app.route("/favicon.ico")
def favicon():
    return send_from_directory(
        str(BASE_DIR / "app" / "static"),
        "aura.ico",
        mimetype="image/x-icon"
    )


@app.route("/")
def index():
    """メイン画面（録音・一覧）"""
    return render_template("index.html", active_page="index")


@app.route("/settings")
def settings():
    """設定画面"""
    return render_template("settings.html", active_page="settings")


# ══════════════════════════════════════════════════
#  録音 API
# ══════════════════════════════════════════════════

@app.route("/api/record/start", methods=["POST"])
def record_start():
    """
    録音を開始する。
    Response: {"status": "started"} or {"status": "error", "message": str}
    """
    result = start()
    status_code = 200 if result["status"] == "started" else 500
    return jsonify(result), status_code


@app.route("/api/record/stop", methods=["POST"])
def record_stop():
    """
    録音を停止してDBに登録する。
    Request JSON（省略可）: {"title": str, "memo": str}
    Response: {"status": "stopped", "record_id": int, "filename": str, "duration": float}
    """
    result = stop()
    if result["status"] == "error":
        return jsonify(result), 500

    # リクエストからタイトル・メモを取得（未入力の場合はデフォルト値）
    data = request.get_json(silent=True) or {}
    title = data.get("title", "無題").strip() or "無題"
    memo = data.get("memo", "").strip()

    # DBに登録
    record_id = create_recording(
        wav_file=result["filename"],
        title=title,
        memo=memo,
    )

    return jsonify({
        "status": "stopped",
        "record_id": record_id,
        "filename": result["filename"],
        "duration": result["duration"],
    }), 200


@app.route("/api/record/status", methods=["GET"])
def record_status():
    """
    現在の録音状態を返す。
    Response: {"recording": bool}
    """
    return jsonify(get_status()), 200


# ══════════════════════════════════════════════════
#  文字起こし & 要約 API
# ══════════════════════════════════════════════════

@app.route("/api/transcribe", methods=["POST"])
def transcribe():
    """
    文字起こしと要約を実行してDBに保存する。
    Request JSON: {"record_id": int}
    Response: {"status": "done", "transcript": str, "ai_summary": str}
    """
    data = request.get_json(silent=True) or {}
    record_id = data.get("record_id")

    if not record_id:
        return jsonify({"status": "error", "message": "record_id が必要です"}), 400

    record = get_recording(record_id)
    if not record:
        return jsonify({"status": "error", "message": "データが見つかりません"}), 404

    extra_prompt = data.get("extra_prompt", "").strip()
    from app.services.transcriber import transcribe_and_summarize
    result = transcribe_and_summarize(record["wav_file"], extra_prompt, record_id)

    if result["status"] == "error":
        return jsonify(result), 500

    # クリーニング済みテキストをDBに保存（個人用モード）
    if result.get("cleaned_transcript"):
        from app.database import update_cleaned_transcript
        update_cleaned_transcript(record_id, result["cleaned_transcript"])

    # DBに保存
    update_transcript_and_summary(record_id, result["transcript"], result["ai_summary"])

    return jsonify({
        "status": "done",
        "transcript": result["transcript"],
        "ai_summary": result["ai_summary"],
    }), 200


# ══════════════════════════════════════════════════
#  録音データ管理 API
# ══════════════════════════════════════════════════

@app.route("/api/recordings", methods=["GET"])
def recordings_list():
    """
    過去の録音データを全件返す。
    Response: [{"id": int, "title": str, ...}, ...]
    """
    return jsonify(get_all_recordings()), 200


@app.route("/api/recordings/<int:record_id>", methods=["PATCH"])
def recordings_update(record_id: int):
    """
    タイトルと概要メモを更新する。
    Request JSON: {"title": str, "memo": str}
    Response: {"status": "updated"} or {"status": "error", "message": str}
    """
    data = request.get_json(silent=True) or {}
    title = data.get("title", "").strip()
    memo = data.get("memo", "").strip()

    if not title:
        return jsonify({"status": "error", "message": "タイトルは必須です"}), 400

    result = update_title_and_memo(record_id, title, memo)
    status_code = 200 if result["status"] == "updated" else 500
    return jsonify(result), status_code


@app.route("/api/recordings/<int:record_id>", methods=["DELETE"])
def recordings_delete(record_id: int):
    """
    録音データをDBとWAVファイルの両方から削除する。
    Response: {"status": "deleted"} or {"status": "error", "message": str}
    """
    # DBから削除（WAVファイル名も返ってくる）
    result = delete_recording(record_id)
    if result["status"] == "error":
        return jsonify(result), 404

    # WAVファイルも削除
    if result.get("wav_file"):
        delete_wav(result["wav_file"])

    return jsonify({"status": "deleted"}), 200



@app.route("/api/recordings/all", methods=["DELETE"])
def recordings_delete_all():
    """
    すべての録音データをDBとWAVファイルの両方から削除する。
    Response: {"status": "deleted", "count": int}
    """
    all_records = get_all_recordings()
    count = 0
    for record in all_records:
        if record.get("wav_file"):
            delete_wav(record["wav_file"])
        delete_recording(record["id"])
        count += 1
    return jsonify({"status": "deleted", "count": count}), 200


# ══════════════════════════════════════════════════
#  音声ファイル配信 API
# ══════════════════════════════════════════════════

if getattr(sys, "frozen", False):
    UPLOADS_DIR = Path(sys.executable).resolve().parent / "uploads"
else:
    UPLOADS_DIR = Path(__file__).resolve().parent / "uploads"

@app.route("/api/audio/<filename>")
def serve_audio(filename):
    """
    WAVファイルをブラウザに配信する（過去データの再生用）。
    ディレクトリトラバーサル対策のため send_from_directory を使用。
    """
    return send_from_directory(str(UPLOADS_DIR), filename)


# ══════════════════════════════════════════════════
#  録音デバイス API
# ══════════════════════════════════════════════════

@app.route("/api/devices", methods=["GET"])
def get_devices():
    """
    利用可能な録音デバイス一覧を返す。
    システム音声デバイス（ステレオミキサー・BlackHole）を自動でハイライト。
    Response: [{"id": int, "name": str, "is_system_audio": bool}, ...]
    """
    import sounddevice as sd
    devices = sd.query_devices()
    result  = []
    # システム音声デバイスのキーワード
    system_keywords = [
        "stereo mix", "ステレオ ミキサー", "ステレオミキサー",
        "blackhole", "black hole",
        "loopback", "what u hear", "wave out mix",
        "virtual audio", "soundflower",
    ]
    for i, dev in enumerate(devices):
        if dev["max_input_channels"] < 1:
            continue  # 入力チャンネルなしはスキップ
        name     = dev["name"]
        is_sys   = any(kw in name.lower() for kw in system_keywords)
        result.append({
            "id":               i,
            "name":             name,
            "is_system_audio":  is_sys,
            "channels":         dev["max_input_channels"],
        })
    return jsonify(result), 200


# ══════════════════════════════════════════════════
#  設定 API
# ══════════════════════════════════════════════════

# PyInstaller frozen 対応
if getattr(sys, "frozen", False):
    ENV_PATH = Path(sys.executable).resolve().parent / ".env"
else:
    ENV_PATH = Path(__file__).resolve().parent / ".env"
print(f"[main] ENV_PATH: {ENV_PATH}")
print(f"[main] frozen: {getattr(sys, 'frozen', False)}")
# 起動時に .env が存在しない場合は空ファイルを作成
if not ENV_PATH.exists():
    ENV_PATH.write_text("AI_MODE=personal\nRECORDING_SOURCE=mic\n", encoding="utf-8")
    print(f"[main] .env を新規作成しました")
print(f"[main] ENV_PATH exists: {ENV_PATH.exists()}")

def _read_env() -> dict:
    """`.env` ファイルを読み込んで辞書で返す"""
    env = {}
    if not ENV_PATH.exists():
        return env
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        env[key.strip()] = val.strip()
    return env

def _write_env(data: dict) -> None:
    """辞書の内容を `.env` ファイルに書き込む（既存の値をマージ）"""
    existing = _read_env()
    existing.update(data)
    lines = [f"{k}={v}" for k, v in existing.items()]
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


@app.route("/api/settings", methods=["GET"])
def settings_get():
    """
    現在の設定を返す（APIキーはマスキング）。
    Response: {"ai_mode": str, "groq_api_key": str}
    """
    env = _read_env()
    api_key = env.get("GROQ_API_KEY", "")
    # 画面表示用に末尾4文字以外をマスク
    masked = ("*" * (len(api_key) - 4) + api_key[-4:]) if len(api_key) > 4 else api_key
    return jsonify({
        "ai_mode":             env.get("AI_MODE", "personal"),
        "groq_api_key":        masked,
        "has_groq_key":        bool(api_key),
        "recording_source":    env.get("RECORDING_SOURCE", "mic"),
        "recording_device_id": env.get("RECORDING_DEVICE_ID", ""),
        "ollama_model":        env.get("OLLAMA_MODEL", "llama3.1:8b"),
    }), 200


@app.route("/api/settings", methods=["POST"])
def settings_save():
    """
    設定を `.env` ファイルに保存する。
    Request JSON: {"ai_mode": str, "groq_api_key": str}
    Response: {"status": "saved"}
    """
    data = request.get_json(silent=True) or {}
    ai_mode    = data.get("ai_mode", "personal")
    groq_key  = data.get("groq_api_key", "").strip()
    device_id = data.get("recording_device_id", "")
    rec_source = data.get("recording_source", "mic")

    ollama_model = data.get("ollama_model", "").strip()
    save_data = {"AI_MODE": ai_mode, "RECORDING_SOURCE": rec_source}
    if ollama_model:
        save_data["OLLAMA_MODEL"] = ollama_model
    # キーが入力されていれば保存（マスク済みの場合は上書きしない）
    if groq_key and not groq_key.startswith("*"):
        save_data["GROQ_API_KEY"] = groq_key
    # デバイスID（空文字・マイナス値は保存しない＝デフォルトデバイス使用）
    if device_id and str(device_id).isdigit():
        save_data["RECORDING_DEVICE_ID"] = str(device_id)

    try:
        _write_env(save_data)
        # ビジネス用モードに切り替えた場合はモデルをバックグラウンドでプリロード
        if ai_mode == "business":
            import platform as _platform
            is_win = _platform.system() == "Windows"
            is_arm = _platform.machine() in ("arm64", "aarch64")
            if is_win or is_arm:
                from app.services.transcriber import preload_model
                preload_model()
        return jsonify({"status": "saved"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500




@app.route("/api/ollama/models", methods=["GET"])
def ollama_models():
    """Ollamaにインストール済みのモデル一覧を返す"""
    import urllib.request
    import json
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags")
        with urllib.request.urlopen(req, timeout=3) as res:
            data = json.loads(res.read().decode("utf-8"))
            models = [m["name"] for m in data.get("models", [])]
            return jsonify({"status": "ok", "models": models}), 200
    except Exception:
        return jsonify({"status": "error", "models": []}), 200

@app.route("/api/ollama/status", methods=["GET"])
def ollama_status():
    """Ollamaの起動状態を確認する"""
    import urllib.request
    try:
        urllib.request.urlopen("http://127.0.0.1:11434", timeout=2)
        return jsonify({"status": "running"}), 200
    except Exception:
        return jsonify({"status": "not_running"}), 200



@app.route("/api/clean", methods=["POST"])
def clean_only():
    """文字起こし済みのレコードに対してクリーニングのみ再実行する"""
    data      = request.get_json(silent=True) or {}
    record_id = data.get("record_id")

    if not record_id:
        return jsonify({"status": "error", "message": "record_id が必要です"}), 400

    record = get_recording(record_id)
    if not record:
        return jsonify({"status": "error", "message": "データが見つかりません"}), 404

    if not record.get("transcript"):
        return jsonify({"status": "error", "message": "文字起こしデータがありません"}), 400

    try:
        env = _read_env()
        ai_mode = env.get("AI_MODE", "personal")

        import app.services.transcriber as _tr
        if ai_mode == "business":
            cleaned = _tr._clean_transcript_ollama(record["transcript"])
        else:
            api_key = env.get("GROQ_API_KEY", "").strip()
            if not api_key:
                return jsonify({"status": "error", "message": "Groq APIキーが設定されていません"}), 400
            from groq import Groq
            client  = Groq(api_key=api_key)
            cleaned = _tr._clean_transcript_groq(client, record["transcript"])

        import app.database as _db
        _db.update_cleaned_transcript(record_id, cleaned)
        return jsonify({"status": "done", "cleaned_transcript": cleaned}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": f"クリーニングエラー: {str(e)}"}), 500

@app.route("/api/summarize", methods=["POST"])
def summarize_only():
    """文字起こし済みのレコードに対して要約のみ再実行する"""
    data      = request.get_json(silent=True) or {}
    record_id = data.get("record_id")

    if not record_id:
        return jsonify({"status": "error", "message": "record_id が必要です"}), 400

    record = get_recording(record_id)
    if not record:
        return jsonify({"status": "error", "message": "データが見つかりません"}), 404

    if not record.get("transcript"):
        return jsonify({"status": "error", "message": "文字起こしデータがありません"}), 400

    try:
        extra_prompt = data.get("extra_prompt", "").strip()
        from app.services.transcriber import _summarize_ollama
        ai_summary = _summarize_ollama(record["transcript"], extra_prompt)
        update_transcript_and_summary(record_id, record["transcript"], ai_summary)
        return jsonify({"status": "done", "ai_summary": ai_summary}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": f"要約エラー: {str(e)}"}), 500

@app.route("/api/model/status", methods=["GET"])
def model_status():
    """
    モデルのダウンロード・ロード状態を返す。
    Response: {"status": "idle"|"downloading"|"ready"|"error", "error": str}
    """
    try:
        from app.services.transcriber import get_model_status
        return jsonify(get_model_status()), 200
    except Exception as e:
        return jsonify({"status": "idle", "error": str(e)}), 200


# ══════════════════════════════════════════════════
#  起動
# ══════════════════════════════════════════════════


def _start_ollama():
    """AURAと一緒にOllamaを起動する（ビジネス用モード時）"""
    import subprocess
    import urllib.request
    # すでに起動しているか確認
    try:
        urllib.request.urlopen("http://127.0.0.1:11434", timeout=2)
        print("[main] Ollamaはすでに起動しています")
        return
    except Exception:
        pass
    # Ollamaを起動
    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("[main] Ollamaを起動しました")
    except Exception as e:
        print(f"[main] Ollama起動エラー: {e}")

def _open_browser():
    """Flaskの起動を待ってからブラウザを開く"""
    import time
    time.sleep(1.5)
    webbrowser.open("http://127.0.0.1:5001")


def _auto_preload_model():
    """起動時にビジネス用モードなら自動でモデルをプリロードする"""
    try:
        env = _read_env()
        if env.get("AI_MODE") == "business":
            import platform as _platform
            is_win = _platform.system() == "Windows"
            is_arm = _platform.machine() in ("arm64", "aarch64")
            if is_win or is_arm:
                from app.services.transcriber import preload_model
                preload_model()
                print("[main] 起動時モデルプリロード開始")
    except Exception as e:
        print(f"[main] 起動時プリロードエラー: {e}")

if __name__ == "__main__":
    # PyInstallerで固めた場合はデバッグ無効・自動リロード無効
    is_frozen = getattr(sys, "frozen", False)

    if not is_frozen:
        # 通常の開発時はデバッグモード
        threading.Thread(target=_start_ollama, daemon=True).start()
        threading.Thread(target=_auto_preload_model, daemon=True).start()
        app.run(host="127.0.0.1", port=5001, debug=True)
    else:
        # 配布用：ブラウザを別スレッドで起動してからFlaskを起動
        print("AURA を起動しています...")
        print("ブラウザが開かない場合は http://127.0.0.1:5001 にアクセスしてください")
        threading.Thread(target=_start_ollama, daemon=True).start()
        threading.Thread(target=_auto_preload_model, daemon=True).start()
        threading.Thread(target=_open_browser, daemon=True).start()
        app.run(host="127.0.0.1", port=5001, debug=False, use_reloader=False)
