import sys

from src.data.load_raw import load_data_config, load_raw_tables
from src.data.validate_schema import validate_raw_tables
from src.db.init_db import init_db


DATA_CONFIG_PATH = "configs/data.yaml"


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python -m src.cli <command>")

    command = sys.argv[1]

    if command == "init-db":
        init_db()
        print("Database initialized.")

    elif command == "validate-raw":
        config = load_data_config(DATA_CONFIG_PATH)
        tables = load_raw_tables(DATA_CONFIG_PATH)
        report = validate_raw_tables(tables, config, strict_fk=False)

        print("Raw data validation completed.")
        for table_name, df in tables.items():
            print(f"{table_name}: shape={df.shape}")

        fk_report = report["fk_report"]
        print(
            f"FK report | {fk_report['relationship_name']} | "
            f"orphans={fk_report['orphan_count']} "
            f"({fk_report['orphan_ratio']:.4%})"
        )

        if fk_report["orphan_count"] > 0:
            print("Sample orphan keys:", fk_report["sample_orphans"])

    else:
        raise SystemExit(f"Unknown command: {command}")


if __name__ == "__main__":
    main()