# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for AnonymizeIt
#
# Build commands:
#   Windows:  pyinstaller anonymise_it.spec
#   macOS:    pyinstaller anonymise_it.spec
#
# The resulting binary will be at:
#   Windows:  dist/AnonymizeIt.exe
#   macOS:    dist/AnonymizeIt
#
# IMPORTANT: Copy your .env file and the public/ folder next to the binary
# after building so runtime configuration and the UI are available.
#
# First-time setup:
#   pip install pyinstaller
#   pip install -r requirements.txt

import sys
import os
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

# ---------------------------------------------------------------------------
# Helper: resolve a package's installation directory
# ---------------------------------------------------------------------------
def pkg_dir(name):
    import importlib
    mod = importlib.import_module(name)
    return os.path.dirname(mod.__file__)


# ---------------------------------------------------------------------------
# Collect everything PyInstaller normally misses for heavy NLP packages
# ---------------------------------------------------------------------------
spacy_datas,    spacy_bins,    spacy_hiddens    = collect_all("spacy")
pydantic_datas, pydantic_bins, pydantic_hiddens = collect_all("pydantic")
presidio_datas, presidio_bins, presidio_hiddens = collect_all("presidio_analyzer")
thinc_datas,    thinc_bins,    thinc_hiddens    = collect_all("thinc")
cymem_datas,    cymem_bins,    cymem_hiddens    = collect_all("cymem")
preshed_datas,  preshed_bins,  preshed_hiddens  = collect_all("preshed")
murmurhash_datas, murmurhash_bins, murmurhash_hiddens = collect_all("murmurhash")
blis_datas,     blis_bins,     blis_hiddens     = collect_all("blis")

# spaCy language models (collected as data only — they ship as pure-Python packages)
en_model_datas, en_model_bins, en_model_hiddens = collect_all("en_core_web_lg")
de_model_datas, de_model_bins, de_model_hiddens = collect_all("de_core_news_lg")

# ---------------------------------------------------------------------------
# Static frontend files
# ---------------------------------------------------------------------------
public_datas = [("public", "public")]

# ---------------------------------------------------------------------------
# All datas / binaries combined
# ---------------------------------------------------------------------------
all_datas = (
    spacy_datas + pydantic_datas + presidio_datas +
    thinc_datas + cymem_datas + preshed_datas +
    murmurhash_datas + blis_datas +
    en_model_datas + de_model_datas +
    public_datas
)

all_binaries = (
    spacy_bins + pydantic_bins + presidio_bins +
    thinc_bins + cymem_bins + preshed_bins +
    murmurhash_bins + blis_bins +
    en_model_bins + de_model_bins
)

all_hiddenimports = (
    spacy_hiddens + pydantic_hiddens + presidio_hiddens +
    thinc_hiddens + cymem_hiddens + preshed_hiddens +
    murmurhash_hiddens + blis_hiddens +
    en_model_hiddens + de_model_hiddens + [
        # FastAPI / Starlette internals
        "uvicorn",
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "fastapi",
        "starlette",
        "starlette.staticfiles",
        "starlette.responses",
        # NLP / ML utilities
        "ahocorasick",
        "phonenumbers",
        "phonenumbers.data",
        # Project packages
        "api",
        "api.anonymise",
        "lib",
        "lib.types",
        "lib.pipeline.index",
        "lib.pipeline.regex_stripper",
        "lib.pipeline.ner_engine",
        "lib.pipeline.blocklist",
        "lib.pipeline.confidence_scorer",
        "lib.pipeline.validator",
    ]
)

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=all_binaries,
    datas=all_datas,
    hiddenimports=all_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude all auth / DB / serverless packages (disabled features)
        "mangum",
        "sqlalchemy",
        "psycopg2",
        "psycopg2-binary",
        "authlib",
        "python_jose",
        "itsdangerous",
        "python_multipart",
        # Heavy unused packages
        "matplotlib",
        "IPython",
        "jupyter",
        "notebook",
        "tkinter",
        "PIL",
        "cv2",
        "pandas",
        "numpy.distutils",
        "scipy",
        "sklearn",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="AnonymizeIt",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,          # Compress the binary (requires UPX; remove if not installed)
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,      # Show console window (needed to see startup logs / errors)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
    onefile=True,      # Single-file bundle
)
