
from distutils.core import setup
import py2exe

setup(
    console=['fit2tcx.py'],
    zipfile=None,
    options={
        "py2exe": {
            "packages": ["lxml"],
            "bundle_files": 1,
            "compressed": True
        }
    })
