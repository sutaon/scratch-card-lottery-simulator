# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

spec_root = Path.cwd()
os.environ['TCL_LIBRARY'] = str(spec_root / 'RuntimeTcl' / 'tcl8.6')
os.environ['TK_LIBRARY'] = str(spec_root / 'RuntimeTcl' / 'tk8.6')

block_cipher = None

added_files = [
    ('Datarecourses/Number.txt', 'Datarecourses'),
    ('Datarecourses/Winning.txt', 'Datarecourses'),
    ('Front', 'Front'),
    ('Picture/app_icon.png', 'Picture'),
    ('Picture/app_icon.ico', 'Picture'),
    ('Picture/Smail.png', 'Picture'),
    ('Picture/StartPicture.jpg', 'Picture'),
    ('Picture/frontPicture', 'Picture/frontPicture'),
    ('RuntimeTcl/tcl8.6', '_tcl_data/tcl8.6'),
    ('RuntimeTcl/tk8.6', '_tk_data/tk8.6')
]

a = Analysis(['main.py'],
             pathex=[],
             binaries=[],
             datas=added_files,
             hiddenimports=['tkinter', '_tkinter'],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          [],
          name='彩票刮刮乐',  # 设置exe名称
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          upx_exclude=[],
          runtime_tmpdir='.',
          console=False,
          icon='Picture/app_icon.ico'  # 设置exe图标路径
          )
