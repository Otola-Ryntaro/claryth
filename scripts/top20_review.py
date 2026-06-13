"""Export, import, and promote medically reviewed PMDA top-20 data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from top20_builder.review import (
    export_review_csv,
    generate_promotion_reports,
    import_review_csv,
    promote_reviewed_database,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    export = commands.add_parser("export")
    export.add_argument("--database", type=Path, default=Path("backend/data/top20_interactions.candidate.sqlite"))
    export.add_argument("--output", type=Path, default=Path("artifacts/top20_review/interactions.csv"))

    review_import = commands.add_parser("import")
    review_import.add_argument("--database", type=Path, default=Path("backend/data/top20_interactions.candidate.sqlite"))
    review_import.add_argument("--review-csv", type=Path, default=Path("artifacts/top20_review/interactions.csv"))

    promote = commands.add_parser("promote")
    promote.add_argument("--database", type=Path, default=Path("backend/data/top20_interactions.candidate.sqlite"))
    promote.add_argument("--output", type=Path, default=Path("backend/data/top20_interactions.sqlite"))
    promote.add_argument("--seed", type=Path, default=Path("backend/data/seed.json"))
    promote.add_argument("--report-dir", type=Path, default=Path("artifacts/top20_promotion"))
    promote.add_argument("--allow-unmapped", action="store_true")

    args = parser.parse_args()
    try:
        if args.command == "export":
            result = {"exported_count": export_review_csv(args.database, args.output), "output": str(args.output)}
        elif args.command == "import":
            result = import_review_csv(args.database, args.review_csv)
        else:
            result = promote_reviewed_database(args.database, args.output)
            report = generate_promotion_reports(args.output, args.seed, args.report_dir)
            if report["unmatched_count"] and not args.allow_unmapped:
                args.output.unlink(missing_ok=True)
                parser.error(
                    f"promotion blocked: {report['unmatched_count']} runtime ingredient mapping(s) are unresolved"
                )
            result["reports"] = report
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (FileNotFoundError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    sys.exit(main())
