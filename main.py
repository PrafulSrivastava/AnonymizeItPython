"""
Standalone entry point for the Text Anonymization API.
Run directly:  python main.py
Run as binary: ./AnonymizeIt  (after building with PyInstaller)
"""

import sys
import os

# When running as a PyInstaller bundle, sys._MEIPASS contains the extracted
# temp directory. We need to ensure our package root is on the path.
if getattr(sys, "frozen", False):
    # Running as compiled executable
    bundle_dir = sys._MEIPASS
    sys.path.insert(0, bundle_dir)

    # Also set working directory so .env and public/ are found relative to
    # the executable itself (not the temp extraction dir)
    exe_dir = os.path.dirname(sys.executable)
    os.chdir(exe_dir)

import uvicorn
from api.anonymise import app

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    print(f"Starting Text Anonymization API on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)
