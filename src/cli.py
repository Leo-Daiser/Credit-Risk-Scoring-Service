import sys
from src.db.init_db import init_db

def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python -m src.cli <command>")

    command = sys.argv[1]

    if command == "init-db":
        init_db()
        print("Database initialized.")
    else:
        raise SystemExit(f"Unknown command: {command}")

if __name__ == "__main__":
    main()