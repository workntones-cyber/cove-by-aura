"""
transcriber.py
文字起こし & AI要約サービス

AIモードに応じて以下を切り替える：
  - personal  : Groq API（Whisper文字起こし + LLaMA要約）
  - business  : faster-whisper（文字起こし）+ Ollama（要約）完全ローカル
"""

import sys
import time
from pathlib import Path

from groq import Groq

# ── 設定 ──────────────────────────────────────────
import sys as _sys
if getattr(_sys, "frozen", False):
    UPLOADS_DIR = Path(_sys.executable).resolve().parent / "uploads"
    ENV_PATH    = Path(_sys.executable).resolve().parent / ".env"
else:
    UPLOADS_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"
    ENV_PATH    = Path(__file__).resolve().parent.parent.parent / ".env"
WHISPER_MODEL      = "whisper-large-v3-turbo"   # 文字起こし用
SUMMARY_MODEL      = "llama-3.3-70b-versatile"  # 要約用
RETRY_COUNT        = 3
RETRY_WAIT         = 30  # 429エラー時のリトライ間隔（秒）


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


# ── メイン関数 ────────────────────────────────────
def transcribe_and_summarize(wav_filename: str, extra_prompt: str = "", record_id: int = None) -> dict:
    """
    WAVファイルを文字起こし & AI要約する。

    Args:
        wav_filename: uploads/ 配下のファイル名（例: aura_20260101_120000.wav）

    Returns:
        {"status": "done", "transcript": str, "ai_summary": str}
        or {"status": "error", "message": str}
    """
    env     = _read_env()
    ai_mode = env.get("AI_MODE", "personal")

    if ai_mode == "business":
        return _transcribe_faster_whisper(wav_filename, extra_prompt, record_id)
    else:
        return _transcribe_groq(wav_filename, env)


# ── Groq API（個人用） ────────────────────────────
def _transcribe_groq(wav_filename: str, env: dict) -> dict:
    api_key = env.get("GROQ_API_KEY", "").strip()
    if not api_key:
        return {
            "status": "error",
            "message": "Groq APIキーが設定されていません。設定画面で入力してください。",
        }

    wav_path = UPLOADS_DIR / wav_filename
    if not wav_path.exists():
        return {"status": "error", "message": f"音声ファイルが見つかりません: {wav_filename}"}

    try:
        client = Groq(api_key=api_key)

        # ── ① 文字起こし（Whisper） ───────────────
        print(f"[transcriber] 文字起こし開始: {wav_filename}")
        raw_transcript = _call_whisper(client, wav_path)
        print(f"[transcriber] 文字起こし完了: {len(raw_transcript)}文字")

        # ── ② 不要文字列除去（Groq LLaMA） ─────────
        print(f"[transcriber] 不要文字列除去開始")
        transcript = _clean_transcript_groq(client, raw_transcript)

        # ── ③ 要約（Groq LLaMA） ─────────────────
        print(f"[transcriber] 要約開始")
        ai_summary = _call_llama(client, transcript)
        print(f"[transcriber] 要約完了: {len(ai_summary)}文字")

        return {
            "status":             "done",
            "transcript":         raw_transcript,
            "cleaned_transcript": transcript,
            "ai_summary":         ai_summary,
        }

    except Exception as e:
        print(f"[transcriber] Groq エラー: {e}")
        return {"status": "error", "message": f"Groq APIエラー: {str(e)}"}


# ── Whisper 文字起こし（チャンク対応・リトライ付き） ──
def _call_whisper(client: Groq, wav_path: Path) -> str:
    """
    WAVファイルを25MB以下のチャンクに分割してWhisperに送信し、
    結果を結合して返す。
    """
    MAX_BYTES = 24 * 1024 * 1024  # 25MB制限に対して余裕を持って24MBに設定

    file_size = wav_path.stat().st_size
    print(f"[transcriber] ファイルサイズ: {file_size / 1024 / 1024:.1f}MB")

    if file_size <= MAX_BYTES:
        # 25MB以下はそのまま送信
        return _send_to_whisper(client, wav_path)

    # 25MB超の場合は時間ベースで分割して送信
    print(f"[transcriber] ファイルが大きいため分割して送信します")
    chunks     = _split_wav(wav_path, MAX_BYTES)
    transcripts = []

    for i, chunk_path in enumerate(chunks):
        print(f"[transcriber] チャンク {i+1}/{len(chunks)} を送信中...")
        text = _send_to_whisper(client, chunk_path)
        transcripts.append(text)
        chunk_path.unlink()  # 一時チャンクを削除

    return " ".join(transcripts)


def _send_to_whisper(client: Groq, wav_path: Path) -> str:
    """単一ファイルをWhisperに送信する（リトライ付き）"""
    for attempt in range(1, RETRY_COUNT + 1):
        try:
            with open(wav_path, "rb") as f:
                response = client.audio.transcriptions.create(
                    file=(wav_path.name, f.read()),
                    model=WHISPER_MODEL,
                    response_format="text",
                    language="ja",
                    temperature=0.0,
                )
            return response.strip() if isinstance(response, str) else response.text.strip()
        except Exception as e:
            if "429" in str(e) and attempt < RETRY_COUNT:
                print(f"[transcriber] 429 レート制限 - {RETRY_WAIT}秒後にリトライ ({attempt}/{RETRY_COUNT})")
                time.sleep(RETRY_WAIT)
            else:
                raise


def _split_wav(wav_path: Path, max_bytes: int) -> list[Path]:
    """WAVファイルをmax_bytes以下のチャンクに分割して一時ファイルとして保存する"""
    import wave as wave_module
    import math

    with wave_module.open(str(wav_path), "rb") as wf:
        n_channels  = wf.getnchannels()
        sampwidth   = wf.getsampwidth()
        framerate   = wf.getframerate()
        n_frames    = wf.getnframes()
        raw         = wf.readframes(n_frames)

    bytes_per_frame  = n_channels * sampwidth
    frames_per_chunk = max_bytes // bytes_per_frame
    total_chunks     = math.ceil(n_frames / frames_per_chunk)
    chunk_paths      = []

    for i in range(total_chunks):
        start      = i * frames_per_chunk * bytes_per_frame
        end        = min(start + frames_per_chunk * bytes_per_frame, len(raw))
        chunk_raw  = raw[start:end]
        chunk_path = wav_path.parent / f"{wav_path.stem}_tmp{i}.wav"

        with wave_module.open(str(chunk_path), "wb") as wf:
            wf.setnchannels(n_channels)
            wf.setsampwidth(sampwidth)
            wf.setframerate(framerate)
            wf.writeframes(chunk_raw)

        chunk_paths.append(chunk_path)
        print(f"[transcriber] 分割チャンク作成: {chunk_path.name} ({len(chunk_raw)/1024/1024:.1f}MB)")

    return chunk_paths


# ── LLaMA 要約（リトライ付き） ────────────────────


def _call_llama_prompt(client, prompt: str) -> str:
    """Groq LLaMAにプロンプトを直接渡して結果を返す"""
    for attempt in range(1, RETRY_COUNT + 1):
        try:
            res = client.chat.completions.create(
                model=SUMMARY_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=8192,
            )
            return res.choices[0].message.content.strip()
        except Exception as e:
            if "429" in str(e) and attempt < RETRY_COUNT:
                print(f"[transcriber] 429 レート制限 - {RETRY_WAIT}秒後にリトライ ({attempt}/{RETRY_COUNT})")
                time.sleep(RETRY_WAIT)
            else:
                raise
    return ""

def _clean_transcript_groq(client, raw_transcript: str) -> str:
    """
    Groq LLaMAを使って文字起こしから不要文字列を除去する（個人用モード）。
    """
    prompt = (
        "以下は会議の音声を文字起こしした生テキストです。\n"
        "以下の種類の文字列を除去して、会議の本質的な内容だけを残してください。\n\n"
        "【除去する文字列の種類】\n"
        "・挨拶（お世話になります、よろしくお願いします、ありがとうございます等）\n"
        "・相槌・短い返答（はい、そうですね、なるほど、とんでもないです等）\n"
        "・フィラー（あー、えーと、うーん、まあ等）\n"
        "・謝罪の定型文（すみません、失礼します等）単独のもの\n"
        "・会議の開始・終了の定型文（では始めます、以上です等）\n\n"
        "【残す文字列】\n"
        "・議題・提案・質問・回答・意見・決定事項\n"
        "・具体的な数字・固有名詞・日付を含む発言\n"
        "・状況説明・背景説明\n\n"
        "除去後のテキストのみ出力してください（説明文・前置きは不要）。\n\n"
        f"【文字起こし】\n{raw_transcript}"
    )
    try:
        cleaned = _call_llama_prompt(client, prompt)
        print(f"[transcriber] Groq クリーニング完了: {len(raw_transcript)}文字 → {len(cleaned)}文字")
        return cleaned if cleaned else raw_transcript
    except Exception as e:
        print(f"[transcriber] Groq クリーニングエラー（元テキストを使用）: {e}")
        return raw_transcript

def _call_llama(client: Groq, transcript: str) -> str:
    prompt = (
        "以下の文字起こし内容を要約してください。\n\n"
        f"【文字起こし】\n{transcript}\n\n"
        "【要約の形式】\n"
        "・重要なポイントを3〜5つの箇条書きでまとめてください。\n"
        "・各ポイントは簡潔に1〜2文で記述してください。\n"
        "・要約のみを出力してください（説明文は不要です）。"
    )

    for attempt in range(1, RETRY_COUNT + 1):
        try:
            response = client.chat.completions.create(
                model=SUMMARY_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            if "429" in str(e) and attempt < RETRY_COUNT:
                print(f"[transcriber] 429 レート制限 - {RETRY_WAIT}秒後にリトライ ({attempt}/{RETRY_COUNT})")
                time.sleep(RETRY_WAIT)
            else:
                raise


# ── faster-whisper（ビジネス用） ───────────────────

# モデルキャッシュ（再利用してメモリ節約）
_whisper_model      = None
_whisper_model_name = None

FASTER_WHISPER_MODEL = "medium"

# モデルダウンロード状態管理
_model_status = "idle"   # idle / downloading / ready / error
_model_error  = ""

def get_model_status() -> dict:
    """モデルのダウンロード・ロード状態を返す"""
    return {
        "status": _model_status,
        "error":  _model_error,
        "model":  FASTER_WHISPER_MODEL,
    }

def preload_model():
    """
    バックグラウンドスレッドでモデルをプリロードする。
    設定画面でビジネス用モードを選択した時点で呼び出す。
    """
    import threading
    t = threading.Thread(target=_preload_model_thread, daemon=True)
    t.start()

def _preload_model_thread():
    global _model_status, _model_error
    if _model_status in ("loading", "ready"):
        return  # すでに進行中またはロード済み
    try:
        _model_status = "loading"
        print("[transcriber] バックグラウンドでモデルをプリロード中...")
        _get_whisper_model()
        _model_status = "ready"
        print("[transcriber] モデルプリロード完了")
    except Exception as e:
        _model_status = "error"
        _model_error  = str(e)
        print(f"[transcriber] モデルプリロードエラー: {e}")


def _get_whisper_model():
    """
    faster-whisperモデルをロードして返す（キャッシュ済みなら再利用）。
    初回はGPU/CPUを自動検出してダウンロードする。
    """
    global _whisper_model, _whisper_model_name

    if _whisper_model is not None and _whisper_model_name == FASTER_WHISPER_MODEL:
        return _whisper_model

    from faster_whisper import WhisperModel

    # GPU(CUDA)が使えるか確認
    try:
        import torch
        if torch.cuda.is_available():
            device    = "cuda"
            compute   = "float16"
            print(f"[transcriber] GPU検出: {torch.cuda.get_device_name(0)}")
        else:
            device    = "cpu"
            compute   = "int8"
            print("[transcriber] GPUなし: CPUで実行します（処理に時間がかかる場合があります）")
    except ImportError:
        device    = "cpu"
        compute   = "int8"
        print("[transcriber] torch未インストール: CPUで実行します")

    # キャッシュの有無を確認してメッセージを出し分け
    import os
    cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
    model_cached = any(
        FASTER_WHISPER_MODEL.replace(".", "-") in str(p)
        for p in cache_dir.glob("**/config.json")
    ) if cache_dir.exists() else False

    if model_cached:
        print(f"[transcriber] Whisperモデルをロード中: {FASTER_WHISPER_MODEL} ({device})")
    else:
        print(f"[transcriber] Whisperモデルをロード中: {FASTER_WHISPER_MODEL} ({device})")
        print("[transcriber] 初回のみ：モデルのダウンロードが発生します（約1.5GB）")

    _whisper_model      = WhisperModel(FASTER_WHISPER_MODEL, device=device, compute_type=compute)
    _whisper_model_name = FASTER_WHISPER_MODEL

    print(f"[transcriber] Whisperモデルのロード完了")
    return _whisper_model



def _get_ollama_model() -> str:
    """使用するOllamaモデルを.envから取得（未設定時はllama3.1:8b）"""
    return _read_env().get("OLLAMA_MODEL", "llama3.1:8b")


def _clean_transcript_ollama(raw_transcript: str) -> str:
    """
    Ollamaを使って文字起こしから不要文字列を除去する。
    挨拶・相槌・フィラー・定型文を削除し本質的な内容のみ残す。
    """
    import urllib.request
    import json

    prompt = (
        "以下は会議の音声を文字起こしした生テキストです。\n"
        "以下の種類の文字列を除去して、会議の本質的な内容だけを残してください。\n\n"
        "【除去する文字列の種類】\n"
        "・挨拶（お世話になります、よろしくお願いします、ありがとうございます等）\n"
        "・相槌・短い返答（はい、そうですね、なるほど、とんでもないです等）\n"
        "・フィラー（あー、えーと、うーん、まあ等）\n"
        "・謝罪の定型文（すみません、失礼します等）単独のもの\n"
        "・会議の開始・終了の定型文（では始めます、以上です等）\n\n"
        "【残す文字列】\n"
        "・議題・提案・質問・回答・意見・決定事項\n"
        "・具体的な数字・固有名詞・日付を含む発言\n"
        "・状況説明・背景説明\n\n"
        "除去後のテキストのみ出力してください（説明文・前置きは不要）。\n\n"
        f"【文字起こし】\n{raw_transcript}"
    )

    payload = json.dumps({
        "model":  _get_ollama_model(),
        "prompt": prompt,
        "stream": False,
    }).encode("utf-8")

    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=None) as res:
            data = json.loads(res.read().decode("utf-8"))
            cleaned = data.get("response", "").strip()
            print(f"[transcriber] Ollama クリーニング完了: {len(raw_transcript)}文字 → {len(cleaned)}文字")
            return cleaned if cleaned else raw_transcript
    except Exception as e:
        print(f"[transcriber] Ollama クリーニングエラー（元テキストを使用）: {e}")
        return raw_transcript  # 失敗時は元テキストをそのまま返す

def _summarize_ollama(transcript: str, extra_prompt: str = "") -> str:
    """
    Ollamaを使ってローカルで要約する。
    完全ローカル処理のため音声データは外部に送信されない。
    """
    import urllib.request
    import json

    prompt = (
        "あなたは経験豊富な議事録作成の専門家です。\n"
        "以下のテキストは実際の会議を録音して文字起こししたものです。\n\n"
        "この会議の文字起こしには以下のような発言が混在しています：\n"
        "・参加者からの質問と、それに対する回答\n"
        "・各参加者の意見・主張・提案\n"
        "・議題に対する賛成・反対・懸念の表明\n"
        "・議論を経て生まれた決定や合意\n"
        "・数字・データ・固有名詞を含む具体的な発言\n\n"
        "これらの発言の種類を正確に区別し、会議の流れと結論が明確にわかる議事録を作成してください。\n\n"
        "【議事録の形式】\n"
        "## 会議の概要\n"
        "（目的・テーマ・参加者・雰囲気を簡潔に）\n\n"
        "## 議題と議論の内容\n"
        "（各議題について「提起された問題・意見・質問→回答・議論の流れ→結論」の形で記載）\n\n"
        "## 決定事項\n"
        "（会議で合意・決定したことをすべて記載。なければ「特になし」）\n\n"
        "## アクションアイテム\n"
        "（誰が・何を・いつまでにするか。なければ「特になし」）\n\n"
        "## 未解決事項・次回への申し送り\n"
        "（結論が出なかった議題・継続検討事項。なければ「特になし」）\n\n"
        "数字・固有名詞・日付・金額は正確に記載してください。\n"
        "議事録のみを出力してください（前置き・説明文は不要です）。\n\n"
        + (f"【追加指示】\n{extra_prompt}\n\n" if extra_prompt else "")
        + f"【会議の文字起こし】\n{transcript}"
    )

    payload = json.dumps({
        "model":  _get_ollama_model(),
        "prompt": prompt,
        "stream": False,
    }).encode("utf-8")

    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=None) as res:  # タイムアウトなし
        data = json.loads(res.read().decode("utf-8"))
        return data.get("response", "").strip()


def _transcribe_faster_whisper(wav_filename: str, extra_prompt: str = "", record_id: int = None) -> dict:
    """
    faster-whisper を使ったローカル文字起こし & LLaMAで要約。
    GPU(CUDA)が使えれば自動でGPU処理、なければCPU処理にフォールバック。
    """
    wav_path = UPLOADS_DIR / wav_filename
    if not wav_path.exists():
        return {"status": "error", "message": f"音声ファイルが見つかりません: {wav_filename}"}

    try:
        model = _get_whisper_model()

        # ── ① 文字起こし ──────────────────────────
        print(f"[transcriber] faster-whisper 文字起こし開始: {wav_filename}")
        # 文字起こし精度向上のための事前情報プロンプト
        initial_prompt = (
            "これは会議・打ち合わせの録音です。"
            "複数の参加者による質疑応答、意見交換、議論が含まれています。"
            "専門用語・固有名詞・数字を正確に文字起こしてください。"
            "よく使われる表現：お世話になります、よろしくお願いします、"
            "ありがとうございます、失礼いたします。"
        )
        segments, info = model.transcribe(
            str(wav_path),
            language="ja",
            beam_size=5,
            initial_prompt=initial_prompt,
            vad_filter=True,       # 無音区間をスキップして高速化
            vad_parameters={"min_silence_duration_ms": 500},
        )
        transcript = " ".join([seg.text.strip() for seg in segments]).strip()
        print(f"[transcriber] faster-whisper 文字起こし完了: {len(transcript)}文字 ({info.duration:.1f}秒)")

        if not transcript:
            return {"status": "error", "message": "文字起こし結果が空でした（無音または認識できませんでした）"}

        # ── ② 不要文字列除去（Ollama） ────────────
        print("[transcriber] Ollama で不要文字列除去開始")
        cleaned = _clean_transcript_ollama(transcript)
        if record_id:
            try:
                from app.database import update_cleaned_transcript
                update_cleaned_transcript(record_id, cleaned)
            except Exception as e:
                print(f"[transcriber] クリーニング保存エラー: {e}")
        transcript = cleaned

        # ── ③ 要約（Ollama ローカル） ─────────────
        print("[transcriber] Ollama で要約開始（完全ローカル処理）")
        try:
            ai_summary = _summarize_ollama(transcript, extra_prompt)
            print(f"[transcriber] Ollama 要約完了: {len(ai_summary)}文字")
        except Exception as e:
            print(f"[transcriber] Ollama 要約エラー: {e}")
            ai_summary = "（要約に失敗しました。Ollamaが起動しているか確認してください）"

        return {
            "status":     "done",
            "transcript": transcript,
            "ai_summary": ai_summary,
        }

    except ImportError:
        return {
            "status":  "error",
            "message": "faster-whisperがインストールされていません。`uv add faster-whisper` を実行してください。",
        }
    except Exception as e:
        print(f"[transcriber] faster-whisper エラー: {e}")
        return {"status": "error", "message": f"faster-whisperエラー: {str(e)}"}
