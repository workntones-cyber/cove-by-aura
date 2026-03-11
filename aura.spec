# -*- mode: python ; coding: utf-8 -*-
# ══════════════════════════════════════════════════
#  AURA - PyInstaller spec ファイル
#
#  ビルド方法：
#    Windows: uv run pyinstaller aura.spec
#    Mac:     uv run pyinstaller aura.spec
#
#  出力先：
#    Windows: dist/AURA.exe
#    Mac:     dist/AURA
# ══════════════════════════════════════════════════

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # テンプレート・静的ファイルを同梱
        ('app/templates', 'app/templates'),
        ('app/static',    'app/static'),
    ],
    hiddenimports=[
        # Flask関連
        'flask',
        'jinja2',
        'werkzeug',
        'click',
        # 音声関連
        'sounddevice',
        'numpy',
        'wave',
        # システム音声録音（Windows WASAPI）
        'pyaudiowpatch',
        'pyaudio',
        # Groq
        'groq',
        # DB
        'sqlite3',
        # 設定
        'dotenv',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='AURA',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,       # コンソールを表示（エラー確認用）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app/static/aura.ico',
)
