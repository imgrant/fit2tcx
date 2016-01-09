# -*- mode: python -*-

block_cipher = None


a = Analysis(['trt2import.py'],
             pathex=['.'],
             binaries=None,
             datas=[(r'C:\Anaconda3\Lib\site-packages\tzwhere\tz_world_compact.json', 'tzwhere')],
             hiddenimports=[],
             hookspath=None,
             runtime_hooks=None,
             excludes=None,
             win_no_prefer_redirects=None,
             win_private_assemblies=None,
             cipher=block_cipher)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          name='trt2import',
          debug=False,
          strip=None,
          upx=True,
          console=True,
          icon='trt2.ico' )
