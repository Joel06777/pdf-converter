import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("STORAGE_DIR", tempfile.mkdtemp(prefix="jobs-"))
os.environ["REDIS_URL"] = ""
os.environ["API_KEY"] = ""
