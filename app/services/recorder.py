import os
import wave
import threading
from datetime import datetime
from pathlib import Path

import numpy as np
import sounddevice as sd

# ── 設定 ──────────────────────────────────────────
SAMPLE_RATE = 16000       # Hz（音声認識最適）
CHANNELS = 1              # モノラル（文字起こしに最適）
DTYPE = "int16"           # 16bit PCM
UPLOADS_DIR = Path(__file__).parent.parent / "uploads"

# ── 状態管理 ──────────────────────────────────────
_recording = False
_frames: list[np.ndarray] = []
_stream: sd.InputStream | None = None
_lock = threading.Lock()


def _ensure_uploads_dir() -> None:
    """uploads/ フォルダが存在しない場合は作成する"""
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def _callback(indata: np.ndarray, frames: int, time, status) -> None:
    """sounddevice のコールバック：録音データをバッファに追加する"""
    if status:
        print(f"[recorder] sounddevice status: {status}")
    with _lock:
        if _recording:
            _frames.append(indata.copy())


def start() -> dict:
    """
    録音を開始する。
    Returns:
        {"status": "started"} or {"status": "error", "message": str}
    """
    global _recording, _frames, _stream

    if _recording:
        return {"status": "error", "message": "すでに録音中です"}

    try:
        _frames = []
        _recording = True
        _stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            callback=_callback,
        )
        _stream.start()
        print("[recorder] 録音開始")
        return {"status": "started"}

    except Exception as e:
        _recording = False
        return {"status": "error", "message": str(e)}


def stop() -> dict:
    """
    録音を停止してWAVファイルに保存する。
    Returns:
        {"status": "stopped", "filename": str, "filepath": str, "duration": float}
        or {"status": "error", "message": str}
    """
    global _recording, _stream

    if not _recording:
        return {"status": "error", "message": "録音中ではありません"}

    try:
        # 録音停止
        _recording = False
        if _stream:
            _stream.stop()
            _stream.close()
            _stream = None

        # フレームが空の場合
        with _lock:
            frames_copy = list(_frames)

        if not frames_copy:
            return {"status": "error", "message": "録音データがありません（無音）"}

        # WAVファイルに保存
        _ensure_uploads_dir()
        filename = f"aura_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
        filepath = UPLOADS_DIR / filename

        audio_data = np.concatenate(frames_copy, axis=0)
        duration = len(audio_data) / SAMPLE_RATE

        with wave.open(str(filepath), "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)           # int16 = 2bytes
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio_data.tobytes())

        # Flaskから配信できるようにファイル権限を設定（macOS対応）
        os.chmod(str(filepath), 0o644)

        print(f"[recorder] 録音停止 → {filename} ({duration:.1f}秒)")
        return {
            "status": "stopped",
            "filename": filename,
            "filepath": str(filepath),
            "duration": round(duration, 1),
        }

    except Exception as e:
        _recording = False
        return {"status": "error", "message": str(e)}


def get_status() -> dict:
    """現在の録音状態を返す"""
    return {"recording": _recording}


def list_recordings() -> list[dict]:
    """
    uploads/ フォルダ内のWAVファイル一覧を返す。
    Returns:
        [{"filename": str, "size_kb": float, "created_at": str}, ...]
    """
    _ensure_uploads_dir()
    files = sorted(UPLOADS_DIR.glob("*.wav"), key=os.path.getmtime, reverse=True)
    result = []
    for f in files:
        stat = f.stat()
        result.append({
            "filename": f.name,
            "filepath": str(f),
            "size_kb": round(stat.st_size / 1024, 1),
            "created_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        })
    return result


def delete_recording(filename: str) -> dict:
    """
    指定したWAVファイルを削除する。
    Args:
        filename: 削除するファイル名（例: aura_20240101_120000.wav）
    Returns:
        {"status": "deleted"} or {"status": "error", "message": str}
    """
    filepath = UPLOADS_DIR / filename

    # ディレクトリトラバーサル対策
    if not filepath.resolve().is_relative_to(UPLOADS_DIR.resolve()):
        return {"status": "error", "message": "不正なファイルパスです"}

    if not filepath.exists():
        return {"status": "error", "message": "ファイルが見つかりません"}

    try:
        filepath.unlink()
        print(f"[recorder] 削除: {filename}")
        return {"status": "deleted"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
