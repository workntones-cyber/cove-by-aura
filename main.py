import os
import sys
import threading
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory

from app.database import (
    create_recording,
    delete_recording,
    delete_all_recordings,
    get_all_recordings,
    get_recording,
    init_db,
    update_title_and_memo,
    update_transcript_and_summary,
    update_recording_category,
    get_all_categories,
    create_category,
    update_category,
    delete_category,
    delete_recordings_by_category,
    get_all_vault_memos,
    create_vault_memo,
    update_vault_memo,
    delete_vault_memo,
    get_all_vault_files,
    create_vault_file,
    update_vault_file_summary,
    delete_vault_file,
    delete_vault_items_by_category,
    # Phase 3
    get_all_persona_settings,
    update_persona_enabled,
    create_council_session,
    update_council_session_decision,
    create_council_adopted,
    get_council_sessions,
    get_context_for_category,
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

@app.route("/vault")
def vault():
    """保管庫画面"""
    return render_template("vault.html", active_page="vault")


@app.route("/council")
def council():
    """相談室画面"""
    return render_template("council.html", active_page="council")


@app.route("/settings")
def settings():
    """設定画面"""
    return render_template("settings.html", active_page="settings")


# ══════════════════════════════════════════════════
#  カテゴリ API
# ══════════════════════════════════════════════════

@app.route("/api/categories", methods=["GET"])
def categories_get():
    """カテゴリ一覧を返す"""
    return jsonify(get_all_categories()), 200


@app.route("/api/categories", methods=["POST"])
def categories_create():
    """カテゴリを新規作成する"""
    data  = request.get_json(silent=True) or {}
    name  = data.get("name", "").strip()
    color = data.get("color", "#6B7280").strip()
    if not name:
        return jsonify({"status": "error", "message": "カテゴリ名は必須です"}), 400
    result = create_category(name, color)
    return jsonify(result), 200 if result["status"] == "ok" else 400


@app.route("/api/categories/<int:category_id>", methods=["PUT"])
def categories_update(category_id):
    """カテゴリ名・色を更新する"""
    data  = request.get_json(silent=True) or {}
    name  = data.get("name", "").strip()
    color = data.get("color", "#6B7280").strip()
    if not name:
        return jsonify({"status": "error", "message": "カテゴリ名は必須です"}), 400
    result = update_category(category_id, name, color)
    return jsonify(result), 200 if result["status"] == "ok" else 400


@app.route("/api/categories/<int:category_id>", methods=["DELETE"])
def categories_delete(category_id):
    """カテゴリを削除しデータを未分類に移動する"""
    result = delete_category(category_id)
    return jsonify(result), 200 if result["status"] == "ok" else 400


@app.route("/api/categories/<int:category_id>/recordings", methods=["DELETE"])
def categories_delete_recordings(category_id):
    """指定カテゴリの録音データを全削除する"""
    count = delete_recordings_by_category(category_id)
    return jsonify({"status": "ok", "deleted": count}), 200


@app.route("/api/recordings/<int:record_id>/category", methods=["PUT"])
def recording_update_category(record_id):
    """録音のカテゴリを更新する"""
    data        = request.get_json(silent=True) or {}
    category_id = data.get("category_id", 1)
    result      = update_recording_category(record_id, category_id)
    return jsonify(result), 200

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




# ══════════════════════════════════════════════════
#  保管庫 API
# ══════════════════════════════════════════════════

VAULT_DIR = BASE_DIR / "vault"
VAULT_DIR.mkdir(exist_ok=True)
_file_summarize_status = {"status": "idle", "message": ""}

@app.route("/api/vault/files/status", methods=["GET"])
def vault_file_status():
    return jsonify(_file_summarize_status), 200

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".pptx", ".txt", ".md"}


@app.route("/api/vault/memos", methods=["GET"])
def vault_memos_get():
    category_id = request.args.get("category_id", type=int)
    return jsonify(get_all_vault_memos(category_id=category_id)), 200


@app.route("/api/vault/memos", methods=["POST"])
def vault_memos_create():
    data        = request.get_json(silent=True) or {}
    title       = data.get("title", "").strip()
    body        = data.get("body", "").strip()
    category_id = int(data.get("category_id", 1) or 1)
    if not body:
        return jsonify({"status": "error", "message": "本文は必須です"}), 400
    memo_id = create_vault_memo(title or "無題", body, category_id)
    return jsonify({"status": "ok", "id": memo_id}), 200


@app.route("/api/vault/memos/<int:memo_id>", methods=["PUT"])
def vault_memos_update(memo_id):
    data        = request.get_json(silent=True) or {}
    title       = data.get("title", "").strip()
    body        = data.get("body", "").strip()
    category_id = int(data.get("category_id", 1) or 1)
    if not body:
        return jsonify({"status": "error", "message": "本文は必須です"}), 400
    return jsonify(update_vault_memo(memo_id, title or "無題", body, category_id)), 200


@app.route("/api/vault/memos/<int:memo_id>", methods=["DELETE"])
def vault_memos_delete(memo_id):
    return jsonify(delete_vault_memo(memo_id)), 200


@app.route("/api/vault/files", methods=["GET"])
def vault_files_get():
    category_id = request.args.get("category_id", type=int)
    return jsonify(get_all_vault_files(category_id=category_id)), 200


@app.route("/api/vault/files", methods=["POST"])
def vault_files_upload():
    """ファイルをアップロードしてOllamaで要約する"""
    if "file" not in request.files:
        return jsonify({"status": "error", "message": "ファイルが選択されていません"}), 400

    file        = request.files["file"]
    category_id = int(request.form.get("category_id", 1) or 1)
    ext         = Path(file.filename).suffix.lower()

    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"status": "error", "message": f"対応していないファイル形式です: {ext}"}), 400

    # ファイルを保存
    import uuid
    filename    = f"{uuid.uuid4().hex}{ext}"
    save_path   = VAULT_DIR / filename
    file.save(str(save_path))

    # DBに登録
    file_id = create_vault_file(filename, file.filename, ext, category_id)

    # バックグラウンドでOllama要約
    def _summarize():
        global _file_summarize_status
        try:
            _file_summarize_status = {"status": "extracting", "message": f"テキストを抽出中: {file.filename}"}
            text = _extract_text(save_path, ext)
            if not text:
                update_vault_file_summary(file_id, "（テキストを抽出できませんでした）")
                _file_summarize_status = {"status": "done", "message": "完了"}
                return
            # 短すぎるテキストはそのまま保存（AIが余計な言い換えをしないよう）
            if len(text) < 200:
                update_vault_file_summary(file_id, text)
                _file_summarize_status = {"status": "done", "message": f"完了: {file.filename}"}
                return

            _file_summarize_status = {"status": "summarizing", "message": f"Ollamaで整形中: {file.filename}"}
            import urllib.request as _ureq2, json as _json2
            from app.services.transcriber import _get_ollama_model
            _file_prompt = (
                "以下はファイルから抽出したテキストです。\n"
                "元の内容を一切変えず・追加せず、そのまま読みやすく整理してください。\n"
                "・重要な数値・固有名詞・日付は正確に残す\n"
                "・箇条書きや見出しを使って構造化する\n"
                "・不要な繰り返しや装飾文字のみ除去する\n"
                "・内容の言い換え・要約・追記は絶対にしないこと\n"
                "整理後のテキストのみ出力してください。\n\n"
                f"{text}"
            )
            _payload2 = _json2.dumps({
                "model": _get_ollama_model(),
                "prompt": _file_prompt,
                "stream": False,
            }).encode("utf-8")
            _req2 = _ureq2.Request(
                "http://127.0.0.1:11434/api/generate",
                data=_payload2,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with _ureq2.urlopen(_req2, timeout=None) as _res2:
                _result2 = _json2.loads(_res2.read().decode("utf-8"))
                summary  = _result2.get("response", "").strip() or text
            update_vault_file_summary(file_id, summary)
            print(f"[vault] ファイル要約完了: {file.filename}")
            _file_summarize_status = {"status": "done", "message": f"完了: {file.filename}"}
        except Exception as e:
            print(f"[vault] ファイル要約エラー: {e}")
            update_vault_file_summary(file_id, f"（整形エラー: {str(e)}）")
            _file_summarize_status = {"status": "error", "message": str(e)}

    import threading
    threading.Thread(target=_summarize, daemon=True).start()

    return jsonify({"status": "ok", "id": file_id, "message": "アップロードしました。要約処理中です。"}), 200


def _extract_text(path: Path, ext: str) -> str:
    """ファイルからテキストを抽出する"""
    try:
        if ext == ".pdf":
            import fitz
            doc  = fitz.open(str(path))
            return "\n".join(page.get_text() for page in doc)
        elif ext == ".docx":
            from docx import Document
            doc = Document(str(path))
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        elif ext == ".xlsx":
            import openpyxl
            wb   = openpyxl.load_workbook(str(path), data_only=True)
            rows = []
            for ws in wb.worksheets:
                for row in ws.iter_rows(values_only=True):
                    r = [str(c) for c in row if c is not None]
                    if r:
                        rows.append("\t".join(r))
            return "\n".join(rows)
        elif ext == ".pptx":
            from pptx import Presentation
            prs  = Presentation(str(path))
            rows = []
            for slide in prs.slides:
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text.strip():
                        rows.append(shape.text)
            return "\n".join(rows)
        elif ext in (".txt", ".md"):
            return path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        print(f"[vault] テキスト抽出エラー: {e}")
    return ""



@app.route("/api/vault/files/<int:file_id>/category", methods=["PUT"])
def vault_file_update_category(file_id):
    """ファイルのカテゴリ・整形内容を更新する"""
    from app.database import get_connection
    data        = request.get_json(silent=True) or {}
    category_id = int(data.get("category_id", 1) or 1)
    summary     = data.get("summary", None)
    with get_connection() as conn:
        if summary is not None:
            conn.execute(
                "UPDATE vault_files SET category_id = ?, summary = ? WHERE id = ?",
                (category_id, summary, file_id)
            )
        else:
            conn.execute(
                "UPDATE vault_files SET category_id = ? WHERE id = ?",
                (category_id, file_id)
            )
        conn.commit()
    return jsonify({"status": "ok"}), 200

@app.route("/api/vault/files/<int:file_id>", methods=["DELETE"])
def vault_files_delete(file_id):
    result = delete_vault_file(file_id)
    if result["status"] == "ok":
        # 実ファイルも削除
        file_path = VAULT_DIR / result["filename"]
        if file_path.exists():
            file_path.unlink()
    return jsonify(result), 200



# Web取得処理の状態管理
_web_fetch_status = {"status": "idle", "message": "", "progress": 0, "total": 0}


@app.route("/api/vault/web/status", methods=["GET"])
def vault_web_status():
    """Web取得処理の状態を返す"""
    return jsonify(_web_fetch_status), 200


@app.route("/api/vault/web/analyze", methods=["POST"])
def vault_web_analyze():
    """URLを解析して同一ドメインのリンク一覧を返す"""
    import urllib.request as _req
    import urllib.parse as _parse
    import html as _html
    import re

    data = request.get_json(silent=True) or {}
    url  = data.get("url", "").strip()
    if not url:
        return jsonify({"status": "error", "message": "URLは必須です"}), 400

    try:
        parsed_base = _parse.urlparse(url)
        base_domain = parsed_base.scheme + "://" + parsed_base.netloc

        headers  = {"User-Agent": "Mozilla/5.0 (compatible; COVE-bot/1.0)"}
        req      = _req.Request(url, headers=headers)
        with _req.urlopen(req, timeout=15) as res:
            raw      = res.read()
            charset  = res.headers.get_content_charset() or "utf-8"
            html_text = raw.decode(charset, errors="ignore")

        # ページタイトル
        title_match = re.search(r"<title[^>]*>([^<]+)</title>", html_text, re.IGNORECASE)
        page_title  = _html.unescape(title_match.group(1).strip()) if title_match else url

        # 同一ドメインのリンクを抽出
        links = []
        seen  = set()
        for href, text in re.findall(r'href=["\']([^"\']+)["\'][^>]*>([^<]*)', html_text):
            href = href.strip()
            text = _html.unescape(text.strip())

            # 相対URLを絶対URLに変換
            if href.startswith('/'):
                href = base_domain + href
            elif not href.startswith('http'):
                continue

            # 同一ドメインのみ
            parsed = _parse.urlparse(href)
            if parsed.netloc != parsed_base.netloc:
                continue

            # フラグメント・クエリを除いたURLで重複チェック
            clean = parsed.scheme + "://" + parsed.netloc + parsed.path
            if clean in seen or clean == url:
                continue
            seen.add(clean)

            links.append({
                "url":   href,
                "title": text or href,
            })

        return jsonify({
            "status":     "ok",
            "page_title": page_title,
            "base_url":   url,
            "links":      links[:100],  # 最大100件表示
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": f"解析エラー: {str(e)}"}), 500


@app.route("/api/vault/web", methods=["POST"])
def vault_web_fetch():
    """選択したURLリストを順番に取得・整形・保管庫に保存する"""
    global _web_fetch_status

    data        = request.get_json(silent=True) or {}
    urls        = data.get("urls", [])
    category_id = int(data.get("category_id", 1) or 1)

    if not urls:
        return jsonify({"status": "error", "message": "URLが選択されていません"}), 400

    def _fetch_all():
        global _web_fetch_status
        import urllib.request as _req
        import urllib.parse as _parse
        import html as _html
        import re

        total = len(urls)
        _web_fetch_status = {"status": "running", "message": f"0 / {total} ページ完了", "progress": 0, "total": total}

        for i, item in enumerate(urls):
            url   = item.get("url", "")
            title = item.get("title", url)
            try:
                _web_fetch_status = {
                    "status":   "running",
                    "message":  f"{i + 1} / {total} ページ取得中: {title[:30]}",
                    "progress": i,
                    "total":    total,
                }

                # ページ取得
                headers = {"User-Agent": "Mozilla/5.0 (compatible; COVE-bot/1.0)"}
                req     = _req.Request(url, headers=headers)
                with _req.urlopen(req, timeout=15) as res:
                    raw     = res.read()
                    charset = res.headers.get_content_charset() or "utf-8"
                    html_text = raw.decode(charset, errors="ignore")

                # タイトル抽出
                title_match = re.search(r"<title[^>]*>([^<]+)</title>", html_text, re.IGNORECASE)
                page_title  = _html.unescape(title_match.group(1).strip()) if title_match else title

                # テキスト抽出
                text = re.sub(r"<script[^>]*>.*?</script>", "", html_text, flags=re.DOTALL|re.IGNORECASE)
                text = re.sub(r"<style[^>]*>.*?</style>",  "", text,      flags=re.DOTALL|re.IGNORECASE)
                text = re.sub(r"<[^>]+>", " ", text)
                text = _html.unescape(text)
                text = re.sub(r"\s+", " ", text).strip()

                if len(text) > 8000:
                    text = text[:8000] + "..."

                if not text:
                    create_vault_memo(page_title, "（テキストを抽出できませんでした）\nURL: " + url, category_id)
                    continue

                # Ollamaで整形
                _web_fetch_status["message"] = f"{i + 1} / {total} 整形中: {page_title[:30]}"
                from app.services.transcriber import _summarize_ollama
                import urllib.request as _ureq
                import json as _json

                prompt = (
                    "以下はWebページから取得したテキストです。\n"
                    "ナビゲーション・フッター・広告・メニュー等の不要な部分を除き、"
                    "本文の情報を欠如なく整理してください。\n"
                    "箇条書きや見出しを使って読みやすく整形してください。\n"
                    "整形後のテキストのみ出力してください。\n\n"
                    f"{text}"
                )

                payload = _json.dumps({
                    "model":  _summarize_ollama.__globals__.get("_get_ollama_model", lambda: "llama3.1:8b")(),
                    "prompt": prompt,
                    "stream": False,
                }).encode("utf-8")

                req2 = _ureq.Request(
                    "http://127.0.0.1:11434/api/generate",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with _ureq.urlopen(req2, timeout=None) as res2:
                    result   = _json.loads(res2.read().decode("utf-8"))
                    arranged = result.get("response", "").strip()

                body = "URL: " + url + "\n\n" + (arranged or text)
                create_vault_memo(page_title, body, category_id)
                print(f"[vault] Web取得完了 ({i+1}/{total}): {page_title}")

            except Exception as e:
                print(f"[vault] Web取得エラー ({url}): {e}")
                create_vault_memo(
                    "取得失敗: " + (title or url),
                    "URL: " + url + "\n\nエラー: " + str(e),
                    category_id
                )

        _web_fetch_status = {
            "status":   "done",
            "message":  f"{total} ページの取得・保存が完了しました",
            "progress": total,
            "total":    total,
        }

    import threading
    threading.Thread(target=_fetch_all, daemon=True).start()
    _web_fetch_status = {"status": "running", "message": "処理を開始しました", "progress": 0, "total": len(urls)}
    return jsonify({"status": "ok", "message": f"{len(urls)}ページの取得を開始しました"}), 200


@app.route("/api/vault/files/<int:file_id>/open-folder", methods=["POST"])
def vault_open_folder(file_id):
    """保存フォルダをエクスプローラーで開く"""
    import subprocess, platform
    if platform.system() == "Windows":
        subprocess.Popen(f'explorer "{VAULT_DIR}"')
    else:
        subprocess.Popen(["open", str(VAULT_DIR)])
    return jsonify({"status": "ok"}), 200




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

    # リクエストからタイトル・メモ・カテゴリを取得
    data        = request.get_json(silent=True) or {}
    title       = data.get("title", "無題").strip() or "無題"
    memo        = data.get("memo", "").strip()
    category_id = int(data.get("category_id", 1) or 1)

    # DBに登録
    record_id = create_recording(
        wav_file=result["filename"],
        title=title,
        memo=memo,
        category_id=category_id,
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
    category_id = request.args.get("category_id", type=int)
    return jsonify(get_all_recordings(category_id=category_id)), 200


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
# 起動時に .env が存在しない場合は空ファイルを作成
if not ENV_PATH.exists():
    ENV_PATH.write_text("AI_MODE=personal\nRECORDING_SOURCE=mic\n", encoding="utf-8")
    print(f"[main] .env を新規作成しました")

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
#  相談室 API
# ══════════════════════════════════════════════════

@app.route("/api/personas", methods=["GET"])
def personas_get():
    """ペルソナ設定一覧を返す"""
    return jsonify(get_all_persona_settings()), 200


@app.route("/api/personas/<string:persona_name>", methods=["PUT"])
def personas_update(persona_name: str):
    """ペルソナのON/OFFを更新する"""
    data    = request.get_json(silent=True) or {}
    enabled = bool(data.get("enabled", True))
    result  = update_persona_enabled(persona_name, enabled)
    return jsonify(result), 200


@app.route("/api/council/ask", methods=["POST"])
def council_ask():
    """
    相談を受け付けてSSEでペルソナ回答をストリーミングする。
    Request JSON: {"question": str, "category_id": int, "personas": [str, ...]}
    SSE events:
      {"type": "start",    "persona": str}
      {"type": "chunk",    "persona": str, "chunk": str}
      {"type": "done",     "persona": str, "answer": str}
      {"type": "finished"}
      {"type": "error",    "message": str}
    """
    import json as _json
    import urllib.request as _ureq
    from app.services.transcriber import _get_ollama_model
    from flask import Response, stream_with_context

    data          = request.get_json(silent=True) or {}
    question      = data.get("question", "").strip()
    category_id   = int(data.get("category_id", 1) or 1)
    persona_names = data.get("personas", [])
    context_keys  = set(data.get("context_keys", None) or [])
    # context_keys が None または未送信 → 全て使う
    # context_keys が空リスト [] → 全てOFF（何も渡さない）
    use_all_context = data.get("context_keys") is None  # キー自体がなければ全使用

    if not question:
        return jsonify({"status": "error", "message": "質問を入力してください"}), 400
    if not persona_names:
        return jsonify({"status": "error", "message": "参加ペルソナがいません"}), 400

    # ── コンテキスト収集（context_keys でフィルタリング）──
    ctx = get_context_for_category(category_id)

    def build_context_text():
        # 全部OFFの場合は空を返す
        if not use_all_context and not context_keys:
            return ""
        parts = []
        for r in ctx.get("recordings", []):
            key = f"rec_{r['id']}"
            if not use_all_context and key not in context_keys:
                continue
            if r.get("ai_summary"):
                parts.append(f"[録音:{r['title']}]\n{r['ai_summary'][:300]}")
        for m in ctx.get("memos", []):
            key = f"memo_{m['id']}"
            if not use_all_context and key not in context_keys:
                continue
            parts.append(f"[メモ:{m['title']}]\n{m['body'][:300]}")
        for f in ctx.get("files", []):
            key = f"file_{f['id']}"
            if not use_all_context and key not in context_keys:
                continue
            if f.get("summary"):
                parts.append(f"[ファイル:{f['original_name']}]\n{f['summary'][:300]}")
        for s in ctx.get("sessions", []):
            if s.get("final_decision"):
                parts.append(f"[過去の決定] 質問:{s['question']} → {s['final_decision']}")
        return "\n\n".join(parts)

    context_text = build_context_text()

    # ── ペルソナ定義（強化版） ──
    PERSONA_SYSTEM = {
        "戦略家": """あなたは20年以上のキャリアを持つ企業戦略顧問です。

【あなたの思考スタイル】
- 勝ちにいくことを最優先。リスクは「織り込み済み」として前進する
- 「できない理由」ではなく「どうすれば勝てるか」だけを考える
- 曖昧な表現・逃げの言葉は使わない。数字と期限で語る
- 競合に勝つためなら大胆な決断も厭わない

【回答の構造】
■結論：一言で断定する（「〜すべきだ」「〜しろ」）
■理由：なぜその判断か、根拠を2点挙げる
■アクション：今すぐ着手すべき具体的な行動を1つ明示する

【制約】
- 400字以内・日本語・敬語不要・断定調
- 自己紹介・前置き・「〜と思います」は禁止
- 必ず具体的なアクションで締める""",

        "リスク管理者": """あなたは大企業のリスク管理部門を15年率いてきた専門家です。

【あなたの思考スタイル】
- 最悪のシナリオを先に想定し、それを防ぐことを最優先する
- 「問題が起きてから対処」ではなく「問題が起きる前に潰す」
- 楽観的な見通しは信用しない。数字の裏を必ず確認する
- リスクを指摘した上で、必ず現実的な対策もセットで提示する

【回答の構造】
■結論：このまま進む場合の最大リスクを一言で
■リスク詳細：見落とされやすい問題点を2〜3点
■対策アクション：リスクを下げるために今すぐできる具体策を1つ

【制約】
- 400字以内・日本語・敬語不要
- 問題点だけでなく必ず対策もセットで述べる
- 具体的なアクションで締める""",

        "アナリスト": """あなたは外資系コンサルティングファーム出身のビジネスアナリストです。

【あなたの思考スタイル】
- 感情・直感・経験談は一切排除。データと論理だけで判断する
- 「なんとなく」「おそらく」は禁句。根拠のない発言はしない
- 仮説を立て、それを検証する思考プロセスを踏む
- 数字がなければ「計測が必要」と明示する

【回答の構造】
■結論：データ・論理に基づく判断を一文で
■根拠：客観的な事実・数値・比較を2点
■次のアクション：意思決定に必要な情報収集または検証行動を1つ具体的に

【制約】
- 400字以内・日本語・敬語不要
- 推測は「推測」と明記する
- 必ず検証可能なアクションで締める""",

        "クリエイター": """あなたは数々のヒット商品を生み出してきたクリエイティブディレクターです。

【あなたの思考スタイル】
- 「前例がない」は褒め言葉。既成概念は破るためにある
- ユーザーが言語化できていないニーズを掘り起こす
- 実現可能性より「面白いか」「誰も思いつかなかったか」を先に考える
- ただし、アイデアは必ず「実行できる形」まで落とし込む

【回答の構造】
■結論：誰も思いつかなかった切り口を一言で
■アイデアの核心：なぜそのアイデアが刺さるか、ユーザー心理と合わせて説明
■最初の一手：アイデアを試すための最小限のアクションを1つ

【制約】
- 400字以内・日本語・敬語不要・エネルギッシュな文体
- ありきたりな提案は禁止
- 必ず「まず〇〇をやれ」という形で締める""",

        "法務・コンプラ": """あなたは上場企業の法務部長として10年以上コンプライアンス管理を担ってきた専門家です。

【あなたの思考スタイル】
- 法令・契約・規制を最優先。「グレーゾーン」は「アウト」として扱う
- 経営判断の前に法的リスクを洗い出すのが自分の役割
- 感情論や売上目標は法的問題の免罪符にはならない
- リスクを指摘するだけでなく、合法的に進める代替案も提示する

【回答の構造】
■結論：法的観点からの判断（「問題なし」「要確認」「要対応」のいずれか）
■法的リスク：該当する可能性のある問題点を具体的に
■対応アクション：法的リスクを回避・軽減するために今すぐ取るべき手続きを1つ

【制約】
- 400字以内・日本語・敬語不要
- 「弁護士に相談すべき」の場合はその旨を明示
- 必ず具体的な手続きアクションで締める""",

        "ユーザー視点": """あなたは現場で10年以上働いてきたユーザー代表・顧客体験の番人です。

【あなたの思考スタイル】
- 「作る側の都合」ではなく「使う側の感情」で考える
- 現場の人間が実際に感じる不満・喜び・面倒くささを代弁する
- 難しい言葉・理想論・きれいごとは通用しない
- 「本当に使われるか」を常に問い続ける

【回答の構造】
■結論：現場ユーザーとして一言で本音を言う
■現場の実態：実際にこういう問題が起きている・起きると思われる具体例
■改善アクション：ユーザーが「これなら使いたい」と思える改善点を1つ具体的に

【制約】
- 400字以内・日本語・敬語不要・率直な口調
- 建前・お世辞は禁止
- 必ずユーザー目線での具体的な改善アクションで締める""",

        "クレーマー": """あなたは何事にも批判的な、最も手強いステークホルダーです。

【あなたの思考スタイル】
- 欠点・矛盾・穴を見つけることに全力を尽くす
- 褒めることは一切しない。それが自分の存在意義
- 「うまくいく前提」で話す人間を信用しない
- どんな計画にも必ず穴がある。それを暴く

【回答の構造】
■致命的な問題：この案の最大の欠陥を一言で断言する
■具体的な批判：見過ごされている問題点を2〜3個、容赦なく指摘する
■突きつける要求：「これをクリアしない限り話にならない」という条件を1つ

【制約】
- 400字以内・日本語・敬語不要・辛辣な文体
- 絶対に褒めない・フォローしない
- 「〜できるのか」「〜するつもりか」という詰める形で締める""",

        "マーケッター": """あなたはD2Cブランドの立ち上げから上場まで経験した実践派マーケティング戦略家です。

【あなたの思考スタイル】
- 「良い商品が売れる」は幻想。売り方・見せ方が全てを決める
- 顧客の「欲しい」より「買わざるを得ない状況」を作ることを考える
- 競合との差別化は機能ではなく「物語」と「ポジション」で生まれる
- 施策は「計測できるか」を必ず確認する

【回答の構造】
■結論：市場で勝つための核心メッセージを一言で
■差別化ポイント：競合との違いをどう打ち出すか、ターゲット像と合わせて説明
■今すぐできるアクション：最小コストで最大効果を得るマーケ施策を1つ具体的に

【制約】
- 400字以内・日本語・敬語不要・キレのある文体
- 抽象的な戦略論は禁止。具体的な施策レベルまで落とす
- 必ず「まず〇〇から始めろ」という形で締める""",
    }

    def generate():
        try:
            env     = _read_env()
            ai_mode = env.get("AI_MODE", "personal")
            model   = _get_ollama_model()

            for persona_name in persona_names:
                system_content = PERSONA_SYSTEM.get(
                    persona_name,
                    f"あなたは{persona_name}の専門家です。質問に対して自分の立場から200字以内で日本語で答えてください。"
                )

                # user メッセージ：コンテキストがあれば添付、なければ質問のみ
                if context_text:
                    user_content = (
                        f"以下の参考情報があります。必要に応じて活用してください。\n\n"
                        f"{context_text}\n\n"
                        f"---\n質問：{question}"
                    )
                else:
                    user_content = f"質問：{question}"

                yield f"data: {_json.dumps({'type': 'start', 'persona': persona_name}, ensure_ascii=False)}\n\n"

                full_answer = ""
                try:
                    if ai_mode == "business":
                        # ── Ollama: /api/chat でロール分離 ──
                        payload = _json.dumps({
                            "model": model,
                            "messages": [
                                {"role": "system", "content": system_content},
                                {"role": "user",   "content": user_content},
                            ],
                            "stream": True,
                            "options": {
                                "temperature": 0.7,
                                "num_predict": 1024,
                                "num_ctx": 2048,
                            },
                        }).encode("utf-8")
                        req = _ureq.Request(
                            "http://127.0.0.1:11434/api/chat",
                            data=payload,
                            headers={"Content-Type": "application/json"},
                            method="POST",
                        )
                        with _ureq.urlopen(req, timeout=60) as res:  # 1ペルソナ最大60秒
                            for line in res:
                                line = line.decode("utf-8").strip()
                                if not line:
                                    continue
                                try:
                                    obj   = _json.loads(line)
                                    chunk = obj.get("message", {}).get("content", "")
                                    if chunk:
                                        full_answer += chunk
                                        yield f"data: {_json.dumps({'type': 'chunk', 'persona': persona_name, 'chunk': chunk}, ensure_ascii=False)}\n\n"
                                    if obj.get("done"):
                                        break
                                except Exception:
                                    pass
                    else:
                        # ── Groq ──
                        api_key = env.get("GROQ_API_KEY", "").strip()
                        if not api_key:
                            raise ValueError("Groq APIキーが未設定です")
                        from groq import Groq
                        client = Groq(api_key=api_key)
                        stream = client.chat.completions.create(
                            model="llama-3.3-70b-versatile",
                            messages=[
                                {"role": "system", "content": system_content},
                                {"role": "user",   "content": user_content},
                            ],
                            max_tokens=400,
                            stream=True,
                        )
                        for chunk_obj in stream:
                            chunk = chunk_obj.choices[0].delta.content or ""
                            if chunk:
                                full_answer += chunk
                                yield f"data: {_json.dumps({'type': 'chunk', 'persona': persona_name, 'chunk': chunk}, ensure_ascii=False)}\n\n"

                except Exception as e:
                    full_answer = f"（エラー: {str(e)}）"
                    yield f"data: {_json.dumps({'type': 'chunk', 'persona': persona_name, 'chunk': full_answer}, ensure_ascii=False)}\n\n"

                yield f"data: {_json.dumps({'type': 'done', 'persona': persona_name, 'answer': full_answer}, ensure_ascii=False)}\n\n"

            yield f"data: {_json.dumps({'type': 'finished'}, ensure_ascii=False)}\n\n"

        except Exception as e:
            yield f"data: {_json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/api/council/save", methods=["POST"])
def council_save():
    """
    相談結果を保存する。
    Request JSON: {"question": str, "category_id": int, "final_decision": str,
                   "adopted": [{"persona_name": str, "answer": str}, ...]}
    """
    data           = request.get_json(silent=True) or {}
    question       = data.get("question", "").strip()
    category_id    = int(data.get("category_id", 1) or 1)
    final_decision = data.get("final_decision", "").strip()
    adopted_list   = data.get("adopted", [])

    if not question:
        return jsonify({"status": "error", "message": "質問は必須です"}), 400

    session_id = create_council_session(question, category_id, final_decision)
    for a in adopted_list:
        pname  = a.get("persona_name", "").strip()
        answer = a.get("answer", "").strip()
        if pname and answer:
            create_council_adopted(session_id, pname, answer)

    return jsonify({"status": "ok", "session_id": session_id}), 200


@app.route("/api/council/sessions", methods=["GET"])
def council_sessions_get():
    """相談履歴を返す"""
    category_id = request.args.get("category_id", type=int)
    sessions    = get_council_sessions(category_id=category_id)
    return jsonify(sessions), 200


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
