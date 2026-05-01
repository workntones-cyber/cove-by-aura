"""
recorder.py
録音サービス

録音ソースに応じて以下を切り替える：
  - mic    : sounddevice（マイク入力）
  - system : soundcard WASAPI ループバック（システム音声・追加設定不要）
  - both   : マイク＋システム音声の同時録音（ミックス）
"""

import os
import sys
import wave
import threading
from datetime import datetime
from pathlib import Path

import numpy as np

# ── 設定 ──────────────────────────────────────────
SAMPLE_RATE   = 16000
CHANNELS      = 1
DTYPE         = "int16"
CHUNK_MINUTES = 10
CHUNK_FRAMES  = SAMPLE_RATE * 60 * CHUNK_MINUTES

if getattr(sys, "frozen", False):
    _BASE       = Path(sys.executable).resolve().parent
    UPLOADS_DIR = _BASE / "uploads"
    ENV_PATH    = _BASE / ".env"
else:
    UPLOADS_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"
    ENV_PATH    = Path(__file__).resolve().parent.parent.parent / ".env"

# ── 状態管理 ──────────────────────────────────────
_recording    = False
_frames: list[np.ndarray] = []
_stream       = None
_lock         = threading.Lock()
_session_id   = ""
_chunk_index  = 0
_frame_count  = 0
_record_thread = None  # soundcard用スレッド


# ── .env 読み込み ─────────────────────────────────
def _read_env() -> dict:
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


def _get_recording_source() -> str:
    return _read_env().get("RECORDING_SOURCE", "mic")


def _get_device_id() -> int | None:
    env = _read_env()
    val = env.get("RECORDING_DEVICE_ID", "").strip()
    if not val or not val.isdigit():
        return None
    try:
        import sounddevice as sd
        device_id = int(val)
        devices   = sd.query_devices()
        if device_id < len(devices) and devices[device_id]["max_input_channels"] > 0:
            return device_id
        print(f"[recorder] デバイスID {device_id} は無効。デフォルトを使用します。")
        return None
    except Exception:
        return None


# ── ファイル操作 ──────────────────────────────────
def _ensure_uploads_dir():
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def _save_wav(filepath: Path, audio_data: np.ndarray):
    with wave.open(str(filepath), "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio_data.tobytes())
    os.chmod(str(filepath), 0o644)


def _flush_chunk(frames: list, session_id: str, chunk_index: int) -> Path:
    _ensure_uploads_dir()
    chunk_path = UPLOADS_DIR / f"{session_id}_part{chunk_index}.wav"
    audio_data = np.concatenate(frames, axis=0)
    _save_wav(chunk_path, audio_data)
    print(f"[recorder] チャンク保存: {chunk_path.name} ({len(audio_data)/SAMPLE_RATE:.1f}秒)")
    return chunk_path


def _merge_chunks(chunk_paths: list) -> np.ndarray:
    all_frames = []
    for path in chunk_paths:
        with wave.open(str(path), "rb") as wf:
            raw = wf.readframes(wf.getnframes())
            all_frames.append(np.frombuffer(raw, dtype=np.int16))
    return np.concatenate(all_frames, axis=0)


# ── sounddevice コールバック（マイク入力） ────────
def _sd_callback(indata, frames, time, status):
    global _frames, _chunk_index, _frame_count
    if status:
        print(f"[recorder] sounddevice status: {status}")
    with _lock:
        if not _recording:
            return
        _frames.append(indata.copy())
        _frame_count += len(indata)
        if _frame_count >= CHUNK_FRAMES:
            _flush_chunk(list(_frames), _session_id, _chunk_index)
            _chunk_index += 1
            _frames       = []
            _frame_count  = 0


# ── BlackHole ループバック録音スレッド（Mac） ─────
def _blackhole_record_thread():
    """
    Mac用：BlackHoleデバイスをsounddeviceで直接録音。
    BlackHoleがインストールされている必要がある。
    """
    global _frames, _chunk_index, _frame_count, _recording

    try:
        import sounddevice as sd

        # BlackHoleデバイスを検索
        devices     = sd.query_devices()
        blackhole_id = None
        for i, dev in enumerate(devices):
            if "blackhole" in dev["name"].lower() and dev["max_input_channels"] > 0:
                blackhole_id = i
                break

        if blackhole_id is None:
            print("[recorder] BlackHoleデバイスが見つかりません。マイクにフォールバックします。")
            blackhole_id = None  # デフォルトデバイスを使用

        print(f"[recorder] BlackHoleデバイスID: {blackhole_id} ({devices[blackhole_id]['name'] if blackhole_id is not None else 'デフォルト'})")

        chunk     = 1024
        src_rate  = int(sd.query_devices(blackhole_id)["default_samplerate"]) if blackhole_id is not None else SAMPLE_RATE
        src_ch    = min(int(sd.query_devices(blackhole_id)["max_input_channels"]), 2) if blackhole_id is not None else CHANNELS

        def _bh_callback(indata, frames, time, status):
            global _frames, _chunk_index, _frame_count
            if status:
                print(f"[recorder] BlackHole status: {status}")
            data = indata.copy()

            # ステレオ→モノラル
            if data.ndim > 1 and data.shape[1] > 1:
                data = data.mean(axis=1)
            else:
                data = data.flatten()

            # サンプルレート変換
            if src_rate != SAMPLE_RATE:
                ratio      = SAMPLE_RATE / src_rate
                new_length = int(len(data) * ratio)
                indices    = np.linspace(0, len(data) - 1, new_length)
                data       = np.interp(indices, np.arange(len(data)), data)

            data_int16 = (np.clip(data, -1.0, 1.0) * 32767).astype(np.int16)

            with _lock:
                _frames.append(data_int16)
                _frame_count += len(data_int16)
                if _frame_count >= CHUNK_FRAMES:
                    _flush_chunk(list(_frames), _session_id, _chunk_index)
                    _chunk_index += 1
                    _frames       = []
                    _frame_count  = 0

        with sd.InputStream(
            device=blackhole_id,
            samplerate=src_rate,
            channels=src_ch,
            dtype="float32",
            blocksize=chunk,
            callback=_bh_callback,
        ):
            while _recording:
                import time as _time
                _time.sleep(0.1)

        print("[recorder] BlackHole録音停止")

    except Exception as e:
        print(f"[recorder] BlackHoleエラー: {e}")
        _recording = False

# ── pyaudiowpatch ループバック録音スレッド（システム音声） ──
def _soundcard_record_thread():
    """
    pyaudiowpatch の WASAPIループバックを使ってシステム音声を録音する。
    追加ドライバー不要でWindows標準機能のみで動作。
    """
    global _frames, _chunk_index, _frame_count, _recording

    try:
        import pyaudiowpatch as pyaudio

        pa       = pyaudio.PyAudio()
        chunk    = 1024

        # WASAPIループバックデバイスを自動検出
        wasapi_info     = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        default_out_idx = wasapi_info["defaultOutputDevice"]
        default_out     = pa.get_device_info_by_index(default_out_idx)

        # ループバックデバイスを探す
        loopback_device = None
        for i in range(pa.get_device_count()):
            dev = pa.get_device_info_by_index(i)
            if (dev.get("isLoopbackDevice", False) and
                default_out["name"] in dev["name"]):
                loopback_device = dev
                loopback_device["index"] = i
                break

        if loopback_device is None:
            # フォールバック：最初のループバックデバイスを使用
            for i in range(pa.get_device_count()):
                dev = pa.get_device_info_by_index(i)
                if dev.get("isLoopbackDevice", False):
                    loopback_device = dev
                    loopback_device["index"] = i
                    break

        if loopback_device is None:
            print("[recorder] WASAPIループバックデバイスが見つかりません")
            _recording = False
            pa.terminate()
            return

        print(f"[recorder] WASAPIループバック: {loopback_device['name']}")

        stream = pa.open(
            format=pyaudio.paInt16,
            channels=int(loopback_device["maxInputChannels"]),
            rate=int(loopback_device["defaultSampleRate"]),
            frames_per_buffer=chunk,
            input=True,
            input_device_index=loopback_device["index"],
        )

        src_channels   = int(loopback_device["maxInputChannels"])
        src_samplerate = int(loopback_device["defaultSampleRate"])

        while _recording:
            raw = stream.read(chunk, exception_on_overflow=False)
            data = np.frombuffer(raw, dtype=np.int16)

            # ステレオ→モノラル変換
            if src_channels > 1:
                data = data.reshape(-1, src_channels).mean(axis=1).astype(np.int16)

            # サンプルレート変換（16000Hz に合わせる）
            if src_samplerate != SAMPLE_RATE:
                ratio      = SAMPLE_RATE / src_samplerate
                new_length = int(len(data) * ratio)
                indices    = np.linspace(0, len(data) - 1, new_length)
                data       = np.interp(indices, np.arange(len(data)), data).astype(np.int16)

            with _lock:
                _frames.append(data)
                _frame_count += len(data)
                if _frame_count >= CHUNK_FRAMES:
                    _flush_chunk(list(_frames), _session_id, _chunk_index)
                    _chunk_index += 1
                    _frames       = []
                    _frame_count  = 0

        stream.stop_stream()
        stream.close()
        pa.terminate()
        print("[recorder] WASAPIループバック録音停止")

    except ImportError:
        print("[recorder] pyaudiowpatch 未インストール。sounddevice にフォールバックします。")
        _recording = False
    except Exception as e:
        print(f"[recorder] pyaudiowpatch エラー: {e}")
        _recording = False


# ── マイクのみ録音（bothのフォールバック） ────────
def _mic_record_thread_fallback() -> None:
    """pyaudiowpatch が使えない場合のマイクのみ録音"""
    import sounddevice as sd
    global _recording, _frames, _frame_count, _chunk_index
    device_id = _get_device_id()
    stream = sd.InputStream(
        device=device_id, samplerate=SAMPLE_RATE,
        channels=CHANNELS, dtype=DTYPE, callback=_sd_callback,
    )
    stream.start()
    while _recording:
        import time; time.sleep(0.1)
    stream.stop()
    stream.close()


# ── マイク＋システム音声 同時録音スレッド（Windows） ──
def _both_record_thread() -> None:
    """
    マイク入力とWASAPIシステム音声を同時録音してミックスする。
    両ストリームを同時に開き、numpy でミックスして _frames に追加する。
    """
    global _recording, _frames, _frame_count, _chunk_index

    import numpy as np

    try:
        import pyaudiowpatch as pyaudio
    except ImportError:
        print("[recorder] pyaudiowpatch 未インストール。マイクのみにフォールバック")
        _mic_record_thread_fallback()
        return

    import sounddevice as sd

    pa = pyaudio.PyAudio()

    # WASAPIループバックデバイスを取得（デフォルト再生デバイス優先）
    wasapi_info      = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
    default_speakers = pa.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
    virtual_keywords = ["vb-audio", "cable", "virtual", "voicemeeter"]
    loopback_dev     = None

    # ① デフォルト再生デバイスのループバックを探す（最優先）
    for i in range(pa.get_device_count()):
        dev = pa.get_device_info_by_index(i)
        if dev.get("hostApi") == wasapi_info["index"] and dev.get("isLoopbackDevice", False):
            if default_speakers["name"] in dev["name"]:
                dev["index"] = i
                loopback_dev = dev
                break

    # ② 見つからない場合は実デバイス優先でフォールバック
    if loopback_dev is None:
        for i in range(pa.get_device_count()):
            dev = pa.get_device_info_by_index(i)
            if dev.get("hostApi") == wasapi_info["index"] and dev.get("isLoopbackDevice", False):
                dev["index"] = i
                name_lower   = dev["name"].lower()
                is_virtual   = any(kw in name_lower for kw in virtual_keywords)
                if loopback_dev is None:
                    loopback_dev = dev
                elif any(kw in loopback_dev["name"].lower() for kw in virtual_keywords) and not is_virtual:
                    loopback_dev = dev

    if loopback_dev is None:
        print("[recorder] WASAPIデバイスが見つかりません。マイクのみ録音します")
        _mic_record_thread_fallback()
        pa.terminate()
        return

    sys_samplerate = int(loopback_dev["defaultSampleRate"])
    sys_channels   = int(loopback_dev["maxInputChannels"])
    chunk_size     = int(sys_samplerate * 0.1)  # 100msチャンク

    print(f"[recorder] 同時録音開始: マイク＋{loopback_dev['name']}")

    # バッファ
    mic_buf  = []
    mic_lock = threading.Lock()

    # マイクコールバック
    def mic_cb(indata, frames, time, status):
        with mic_lock:
            mic_buf.append(indata.copy())

    # システム音声ストリーム
    sys_stream = pa.open(
        format=pyaudio.paInt16,
        channels=sys_channels,
        rate=sys_samplerate,
        input=True,
        input_device_index=loopback_dev["index"],
        frames_per_buffer=chunk_size,
    )

    device_id = _get_device_id()
    mic_stream = sd.InputStream(
        device=device_id,
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype=DTYPE,
        callback=mic_cb,
        blocksize=int(SAMPLE_RATE * 0.1),
    )

    sys_stream.start_stream()
    mic_stream.start()

    try:
        while _recording:
            # システム音声を読み込み
            raw = sys_stream.read(chunk_size, exception_on_overflow=False)
            sys_arr = np.frombuffer(raw, dtype=np.int16)
            if sys_arr.ndim == 0 or sys_arr.size == 0:
                continue

            # ステレオ→モノラル変換
            if sys_channels > 1:
                try:
                    sys_arr = sys_arr.reshape(-1, sys_channels).mean(axis=1).astype(np.int16)
                except Exception:
                    continue

            # サンプルレート変換（16000Hzに統一）
            if sys_samplerate != SAMPLE_RATE and len(sys_arr) > 0:
                ratio   = SAMPLE_RATE / sys_samplerate
                new_len = max(1, int(len(sys_arr) * ratio))
                indices = np.linspace(0, len(sys_arr) - 1, new_len)
                sys_arr = np.interp(indices, np.arange(len(sys_arr)), sys_arr).astype(np.int16)

            if len(sys_arr) == 0:
                continue

            # マイクバッファを取得
            with mic_lock:
                valid = [a for a in mic_buf if isinstance(a, np.ndarray) and a.ndim > 0 and a.size > 0]
                mic_buf.clear()

            if valid:
                try:
                    mic_arr = np.concatenate([a.flatten() for a in valid]).astype(np.int16)
                except Exception:
                    mic_arr = np.zeros(len(sys_arr), dtype=np.int16)
            else:
                mic_arr = np.zeros(len(sys_arr), dtype=np.int16)

            # 長さを揃えてミックス
            min_len = min(len(sys_arr), len(mic_arr))
            if min_len == 0:
                continue
            sys_arr = sys_arr[:min_len]
            mic_arr = mic_arr[:min_len]

            mixed = np.clip(
                sys_arr.astype(np.float32) * 0.6 + mic_arr.astype(np.float32) * 0.6,
                -32768, 32767
            ).astype(np.int16)

            with _lock:
                _frames.append(mixed)
                _frame_count += len(mixed)
                if _frame_count >= CHUNK_FRAMES:
                    _flush_chunk(list(_frames), _session_id, _chunk_index)
                    _frames      = []
                    _frame_count = 0
                    _chunk_index += 1

    finally:
        mic_stream.stop()
        mic_stream.close()
        sys_stream.stop_stream()
        sys_stream.close()
        pa.terminate()
        print("[recorder] 同時録音停止")


# ── 録音開始 ──────────────────────────────────────
def start() -> dict:
    global _recording, _frames, _stream, _session_id, _chunk_index, _frame_count, _record_thread

    if _recording:
        return {"status": "error", "message": "すでに録音中です"}

    try:
        _session_id  = f"cove_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        _frames      = []
        _chunk_index = 0
        _frame_count = 0
        _recording   = True
        source       = _get_recording_source()

        if source == "both":
            import platform
            if platform.system() == "Windows":
                _record_thread = threading.Thread(target=_both_record_thread, daemon=True)
                _record_thread.start()
                print(f"[recorder] マイク＋システム音声同時録音開始: {_session_id}")
            else:
                # Mac: 未対応のためマイクのみにフォールバック
                import sounddevice as sd
                device_id = _get_device_id()
                _stream = sd.InputStream(
                    device=device_id, samplerate=SAMPLE_RATE,
                    channels=CHANNELS, dtype=DTYPE, callback=_sd_callback,
                )
                _stream.start()
                print(f"[recorder] Mac同時録音未対応: マイクのみで録音開始: {_session_id}")
        elif source == "system":
            import platform
            if platform.system() == "Windows":
                # Windows: pyaudiowpatch WASAPIループバック
                _record_thread = threading.Thread(target=_soundcard_record_thread, daemon=True)
                _record_thread.start()
                print(f"[recorder] システム音声録音開始 (pyaudiowpatch WASAPI): {_session_id}")
            else:
                # Mac: BlackHole経由でsounddeviceで録音
                _record_thread = threading.Thread(target=_blackhole_record_thread, daemon=True)
                _record_thread.start()
                print(f"[recorder] システム音声録音開始 (BlackHole): {_session_id}")
        else:
            # sounddevice（マイク入力）
            import sounddevice as sd
            device_id = _get_device_id()
            print(f"[recorder] マイク録音開始 デバイス:{device_id if device_id is not None else 'デフォルト'}: {_session_id}")
            _stream = sd.InputStream(
                device=device_id,
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype=DTYPE,
                callback=_sd_callback,
            )
            _stream.start()

        return {"status": "started"}

    except Exception as e:
        _recording = False
        return {"status": "error", "message": str(e)}


# ── 録音停止 ──────────────────────────────────────
def stop() -> dict:
    global _recording, _stream, _record_thread

    if not _recording:
        return {"status": "error", "message": "録音中ではありません"}

    try:
        _recording = False

        # sounddevice停止
        if _stream:
            _stream.stop()
            _stream.close()
            _stream = None

        # soundcardスレッド終了待ち
        if _record_thread and _record_thread.is_alive():
            _record_thread.join(timeout=3)
            _record_thread = None

        with _lock:
            remaining_frames = list(_frames)

        _ensure_uploads_dir()
        if remaining_frames:
            _flush_chunk(remaining_frames, _session_id, _chunk_index)
            total_chunks = _chunk_index + 1
        else:
            total_chunks = _chunk_index

        if total_chunks == 0:
            return {"status": "error", "message": "録音データがありません（無音）"}

        chunk_paths = sorted(
            UPLOADS_DIR.glob(f"{_session_id}_part*.wav"),
            key=lambda p: int(p.stem.split("_part")[1])
        )

        main_filename = f"{_session_id}.wav"
        main_filepath = UPLOADS_DIR / main_filename
        all_audio     = _merge_chunks(chunk_paths)
        _save_wav(main_filepath, all_audio)
        duration      = len(all_audio) / SAMPLE_RATE

        for p in chunk_paths:
            p.unlink()

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


def get_status() -> dict:
    return {"recording": _recording}


def list_recordings() -> list[dict]:
    _ensure_uploads_dir()
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
    filepath = UPLOADS_DIR / filename
    if not filepath.resolve().is_relative_to(UPLOADS_DIR.resolve()):
        return {"status": "error", "message": "不正なファイルパスです"}
    if not filepath.exists():
        return {"status": "error", "message": "ファイルが見つかりません"}
    try:
        filepath.unlink()
        return {"status": "deleted"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
