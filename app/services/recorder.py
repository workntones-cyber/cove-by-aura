import os
import wave
import threading
from datetime import datetime
from pathlib import Path

import numpy as np
import sounddevice as sd

# ── 設定 ──────────────────────────────────────────
SAMPLE_RATE  = 16000        # Hz（音声認識最適）
CHANNELS     = 1            # モノラル（文字起こしに最適）
DTYPE        = "int16"      # 16bit PCM
CHUNK_MINUTES = 10          # 自動分割間隔（分）
CHUNK_FRAMES  = SAMPLE_RATE * 60 * CHUNK_MINUTES  # 1チャンクのフレーム数
UPLOADS_DIR  = Path(__file__).resolve().parent.parent.parent / "uploads"

# ── 状態管理 ──────────────────────────────────────
_recording   = False
_frames: list[np.ndarray] = []
_stream: sd.InputStream | None = None
_lock        = threading.Lock()
_session_id  = ""           # 録音セッションID（チャンクファイルの命名に使用）
_chunk_index = 0            # 現在のチャンク番号
_frame_count = 0            # 現在のチャンク内フレーム数


def _ensure_uploads_dir() -> None:
    """uploads/ フォルダが存在しない場合は作成する"""
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def _save_wav(filepath: Path, audio_data: np.ndarray) -> None:
    """音声データをWAVファイルに保存し、パーミッションを設定する"""
    with wave.open(str(filepath), "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)  # int16 = 2bytes
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio_data.tobytes())
    os.chmod(str(filepath), 0o644)  # macOS対応


def _flush_chunk(frames: list[np.ndarray], session_id: str, chunk_index: int) -> Path:
    """
    現在のフレームバッファをチャンクWAVファイルとして保存する。
    Returns: 保存したファイルのパス
    """
    _ensure_uploads_dir()
    chunk_path = UPLOADS_DIR / f"{session_id}_part{chunk_index}.wav"
    audio_data = np.concatenate(frames, axis=0)
    _save_wav(chunk_path, audio_data)
    print(f"[recorder] チャンク保存: {chunk_path.name} ({len(audio_data)/SAMPLE_RATE:.1f}秒)")
    return chunk_path


def _callback(indata: np.ndarray, frames: int, time, status) -> None:
    """
    sounddevice のコールバック。
    CHUNK_FRAMES を超えたら自動でチャンクファイルを保存する。
    """
    global _frames, _chunk_index, _frame_count

    if status:
        print(f"[recorder] sounddevice status: {status}")

    with _lock:
        if not _recording:
            return

        _frames.append(indata.copy())
        _frame_count += len(indata)

        # チャンクサイズを超えたら自動分割
        if _frame_count >= CHUNK_FRAMES:
            frames_to_save = list(_frames)
            _flush_chunk(frames_to_save, _session_id, _chunk_index)
            _chunk_index += 1
            _frames = []
            _frame_count = 0


def start() -> dict:
    """
    録音を開始する。
    Returns:
        {"status": "started"} or {"status": "error", "message": str}
    """
    global _recording, _frames, _stream, _session_id, _chunk_index, _frame_count

    if _recording:
        return {"status": "error", "message": "すでに録音中です"}

    try:
        _session_id  = f"aura_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        _frames      = []
        _chunk_index = 0
        _frame_count = 0
        _recording   = True

        _stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            callback=_callback,
        )
        _stream.start()
        print(f"[recorder] 録音開始: {_session_id}")
        return {"status": "started"}

    except Exception as e:
        _recording = False
        return {"status": "error", "message": str(e)}


def stop() -> dict:
    """
    録音を停止する。
    チャンクファイルをすべて結合してメインWAVファイルを作成する。

    Returns:
        {
            "status": "stopped",
            "filename": str,       # メインWAVファイル名
            "filepath": str,
            "duration": float,     # 録音時間（秒）
            "chunks": int,         # 分割数
        }
        or {"status": "error", "message": str}
    """
    global _recording, _stream

    if not _recording:
        return {"status": "error", "message": "録音中ではありません"}

    try:
        _recording = False
        if _stream:
            _stream.stop()
            _stream.close()
            _stream = None

        with _lock:
            remaining_frames = list(_frames)

        # 残りフレームをチャンクとして保存
        _ensure_uploads_dir()
        if remaining_frames:
            _flush_chunk(remaining_frames, _session_id, _chunk_index)
            total_chunks = _chunk_index + 1
        else:
            total_chunks = _chunk_index

        if total_chunks == 0:
            return {"status": "error", "message": "録音データがありません（無音）"}

        # チャンクファイルを収集
        chunk_paths = sorted(
            UPLOADS_DIR.glob(f"{_session_id}_part*.wav"),
            key=lambda p: int(p.stem.split("_part")[1])
        )

        # 全チャンクを結合してメインWAVを作成
        main_filename = f"{_session_id}.wav"
        main_filepath = UPLOADS_DIR / main_filename
        all_audio     = _merge_chunks(chunk_paths)
        _save_wav(main_filepath, all_audio)
        duration      = len(all_audio) / SAMPLE_RATE

        # チャンクファイルを削除
        for p in chunk_paths:
            p.unlink()
            print(f"[recorder] チャンク削除: {p.name}")

        print(f"[recorder] 録音完了: {main_filename} ({duration:.1f}秒, {total_chunks}チャンク)")
        return {
            "status":   "stopped",
            "filename": main_filename,
            "filepath": str(main_filepath),
            "duration": round(duration, 1),
            "chunks":   total_chunks,
        }

    except Exception as e:
        _recording = False
        return {"status": "error", "message": str(e)}


def _merge_chunks(chunk_paths: list[Path]) -> np.ndarray:
    """複数のWAVチャンクファイルを1つのndarrayに結合する"""
    all_frames = []
    for path in chunk_paths:
        with wave.open(str(path), "rb") as wf:
            raw = wf.readframes(wf.getnframes())
            all_frames.append(np.frombuffer(raw, dtype=np.int16))
    return np.concatenate(all_frames, axis=0)


def get_status() -> dict:
    """現在の録音状態と経過時間を返す"""
    return {"recording": _recording}


def list_recordings() -> list[dict]:
    """
    uploads/ フォルダ内のWAVファイル一覧を返す（チャンクファイルは除外）。
    """
    _ensure_uploads_dir()
    # _partN.wav はチャンクファイルなので除外
    files = sorted(
        [f for f in UPLOADS_DIR.glob("*.wav") if "_part" not in f.name],
        key=os.path.getmtime,
        reverse=True,
    )
    result = []
    for f in files:
        stat = f.stat()
        result.append({
            "filename":   f.name,
            "filepath":   str(f),
            "size_kb":    round(stat.st_size / 1024, 1),
            "created_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        })
    return result


def delete_recording(filename: str) -> dict:
    """
    指定したWAVファイルを削除する。
    """
    filepath = UPLOADS_DIR / filename

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
