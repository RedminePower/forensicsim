# -*- mode: python ; coding: utf-8 -*-

block_cipher = None


a = Analysis(['tools\\main.py'],
             binaries=[],
             datas=[],
             hiddenimports=[],
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
          [],
          exclude_binaries=True,
          name='ms_teams_parser',
          debug=False,
          strip=False,
          upx=False,
          runtime_tmpdir=None,
          console=True )
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=False,
               upx_exclude=[],
               name='ms_teams_parser')

# Pack the onedir output into a single distributable zip so the parent
# project can vendor one tracked artifact instead of the loose folder.
# shutil.make_archive uses ZIP_DEFLATED, matching the previously hand-built zip.
import os
import shutil

bundle_name = 'ms_teams_parser'
zip_path = os.path.join(DISTPATH, bundle_name + '.zip')
if os.path.exists(zip_path):
    os.remove(zip_path)
shutil.make_archive(os.path.join(DISTPATH, bundle_name), 'zip',
                    root_dir=DISTPATH, base_dir=bundle_name)
