"""
SnapMemory launcher.

    python run.py

Opens the app at http://127.0.0.1:5057
"""
from db import database
from app import app

if __name__ == "__main__":
    database.init_db()
    print("SnapMemory starting at http://127.0.0.1:5057")
    print("Everything below this line runs locally. No cloud calls are made by the core system.")
    app.run(host="127.0.0.1", port=5057, debug=False, threaded=True)
