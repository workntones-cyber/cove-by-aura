# -*- mode: python ; coding: utf-8 -*-
# cove.spec - PyInstaller build spec for COVE by AURA
# 使用方法: uv run pyinstaller cove.spec

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # テンプレート
        ('app/templates',        'app/templates'),
        # 静的ファイル
        ('app/static',           'app/static'),
        # アプリケーションモジュール
        ('app/database.py',      'app'),
        ('app/services',         'app/services'),
        ('app/services/llm',     'app/services/llm'),
        # アイコン（PyInstaller用）
        ('cove.ico',             '.'),
    ],
    hiddenimports=[
        # Flask関連
        'flask',
        'flask.templating',
        'jinja2',
        'werkzeug',
        'werkzeug.serving',
        'werkzeug.middleware.shared_data',
        # faster-whisper関連
        'faster_whisper',
        'ctranslate2',
        'tokenizers',
        'huggingface_hub',
        # 音声処理
        'sounddevice',
        'soundfile',
        'numpy',
        # DB
        'sqlite3',
        # その他
        'requests',
        'urllib',
        'urllib.request',
        'threading',
        'pathlib',
        'json',
        'os',
        're',
        'subprocess',
        'psutil',
        # クラウドAI
        'groq',
        'anthropic',
        'openai',
        'google.generativeai',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 不要なもの
        'tkinter',
        'matplotlib',
        'PIL',
        'cv2',
        'scipy',
        'pandas',
        'IPython',
        'jupyter',
        'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='COVE',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,          # ログ確認のためコンソールを表示
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # アイコン（Windows: .ico / Mac: .icns）
    icon='cove.ico' if sys.platform == 'win32' else 'cove.iconset/icon_512x512.png',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='COVE',
)
