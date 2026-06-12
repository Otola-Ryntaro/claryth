"""Rebuild the local SQLite database from the reviewable JSON seed."""

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.database import initialize_database


if __name__ == "__main__":
    initialize_database()
    print("backend/data/clarith.db を更新しました")
