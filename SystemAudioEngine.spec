# -*- mode: python ; coding: utf-8 -*-

import os
import sys
import certifi

cert_path = certifi.where()

datas = [
    ('.env', '.'),
    ('logo.png', '.'),
    ('app_icon.ico', '.'),
    ('overlay_icon.ico', '.'),
    ('chat_history.json', '.'),
    ('browser_tab.py', '.'),
    ('overlay.py', '.'),
    ('overlay.html', '.'),
    (cert_path, 'certifi')
]

if os.path.exists('icons'):
    datas.append(('icons', 'icons'))

a = Analysis(
    ['overlay.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'PyQt5.QtWebEngineWidgets',
        'PyQt5.QtWebEngineCore',
        'PyQt5.QtNetwork',
        'google.genai',
        'PIL',
        'groq',
        'openai',
        'googlesearch',
        'pygments',
        'mss',
        'dotenv',
        'core',
        'core.constants',
        'core.stealth',
        'ai',
        'ai.web2api',
        'ai.worker',
        'ai.vision_worker',
        'ui',
        'ui.widgets',
        'ui.snip',
        'ui.event_filter',
        'features',
        'features.voice',
        'utils',
        'utils.typing_engine',
        'certifi'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'unittest', 'matplotlib', 'numpy.random._examples',
        'scipy', 'pandas', 'IPython', 'notebook', 'tensorflow', 'torch'
    ],
    noarchive=False,
    optimize=2,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SystemAudioEngine',
    debug=False,
    bootloader_ignore_signals=False,
    icon='app_icon.ico',
    version='file_version_info.txt',
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='SystemAudioEngine',
)
