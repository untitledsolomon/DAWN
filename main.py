"""
Root launcher for the DAWN API.

The real application lives in dawn-api/main.py. This shim lets you run
`uvicorn main:app` from the repository root (D:\\Projects\\DAWN) instead of
having to cd into dawn-api first. It puts dawn-api on the import path and
re-exports the FastAPI app.
"""
import importlib.util
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
_api_dir = os.path.join(_here, "dawn-api")
if _api_dir not in sys.path:
    sys.path.insert(0, _api_dir)

# Load dawn-api/main.py under a distinct module name so it doesn't collide
# with this shim (both would otherwise be importable as `main`).
_api_main_path = os.path.join(_api_dir, "main.py")
_spec = importlib.util.spec_from_file_location("dawn_api_main", _api_main_path)
_dawn_api_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_dawn_api_main)

app = _dawn_api_main.app
