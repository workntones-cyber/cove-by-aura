import os
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

app = Flask(__name__, template_folder="app/templates", static_folder="app/static")

# ── 起動時にDBを初期化 ────────────────────────────
init_db()


# ══════════════════════════════════════════════════
#  ページルーティング
# ══════════════════════════════════════════════════

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

    # transcriber.py は次のステップで実装
    # from app.services.transcriber import transcribe_and_summarize
    # result = transcribe_and_summarize(record["wav_file"])

    # ── 暫定：ダミーレスポンス（transcriber.py実装後に差し替え）──
    transcript = "（文字起こし結果がここに入ります）"
    ai_summary = "（AI要約結果がここに入ります）"

    # DBに保存
    update_transcript_and_summary(record_id, transcript, ai_summary)

    return jsonify({
        "status": "done",
        "transcript": transcript,
        "ai_summary": ai_summary,
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


# ══════════════════════════════════════════════════
#  音声ファイル配信 API
# ══════════════════════════════════════════════════

UPLOADS_DIR = Path(__file__).resolve().parent / "uploads"

@app.route("/api/audio/<filename>")
def serve_audio(filename):
    """
    WAVファイルをブラウザに配信する（過去データの再生用）。
    ディレクトリトラバーサル対策のため send_from_directory を使用。
    """
    return send_from_directory(str(UPLOADS_DIR), filename)


# ══════════════════════════════════════════════════
#  設定 API
# ══════════════════════════════════════════════════

ENV_PATH = Path(__file__).parent / ".env"

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
    Response: {"ai_mode": str, "gemini_api_key": str}
    """
    env = _read_env()
    api_key = env.get("GEMINI_API_KEY", "")
    # 画面表示用に末尾4文字以外をマスク
    masked = ("*" * (len(api_key) - 4) + api_key[-4:]) if len(api_key) > 4 else api_key
    return jsonify({
        "ai_mode": env.get("AI_MODE", "personal"),
        "gemini_api_key": masked,
    }), 200


@app.route("/api/settings", methods=["POST"])
def settings_save():
    """
    設定を `.env` ファイルに保存する。
    Request JSON: {"ai_mode": str, "gemini_api_key": str}
    Response: {"status": "saved"}
    """
    data = request.get_json(silent=True) or {}
    ai_mode    = data.get("ai_mode", "personal")
    gemini_key = data.get("gemini_api_key", "").strip()

    save_data = {"AI_MODE": ai_mode}
    # キーが入力されていれば保存（マスク済みの場合は上書きしない）
    if gemini_key and not gemini_key.startswith("*"):
        save_data["GEMINI_API_KEY"] = gemini_key

    try:
        _write_env(save_data)
        return jsonify({"status": "saved"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ══════════════════════════════════════════════════
#  起動
# ══════════════════════════════════════════════════

if __name__ == "__main__":
    app.run(debug=True)
