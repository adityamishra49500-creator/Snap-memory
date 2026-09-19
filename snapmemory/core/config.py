"""
SnapMemory — central configuration.

Everything here is read from environment variables with safe local defaults.
No API keys are required for the core (local-first) system to function.
"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("SNAPMEMORY_DATA_DIR", os.path.join(BASE_DIR, "data"))
DB_PATH = os.path.join(DATA_DIR, "snapmemory.db")
FILES_DIR = os.path.join(DATA_DIR, "files")
AUDIT_LOG_PATH = os.path.join(DATA_DIR, "audit.log")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(FILES_DIR, exist_ok=True)

# Chunking
CHUNK_SIZE_CHARS = int(os.environ.get("SNAPMEMORY_CHUNK_SIZE", 900))
CHUNK_OVERLAP_CHARS = int(os.environ.get("SNAPMEMORY_CHUNK_OVERLAP", 150))

# Retrieval
DEFAULT_TOP_K = int(os.environ.get("SNAPMEMORY_TOP_K", 5))
DEFAULT_SIMILARITY_THRESHOLD = float(os.environ.get("SNAPMEMORY_SIM_THRESHOLD", 0.05))
MAX_CONTEXT_CHARS = int(os.environ.get("SNAPMEMORY_MAX_CONTEXT_CHARS", 6000))

# Explicit, honest capability flags. These are DETECTED at runtime, not assumed.
# See ai/providers.py for how these are actually verified.
ALLOW_CLOUD_FALLBACK = os.environ.get("SNAPMEMORY_ALLOW_CLOUD_FALLBACK", "0") == "1"

APP_NAME = "SnapMemory"
TAGLINE = "Remember everything. Share nothing."
