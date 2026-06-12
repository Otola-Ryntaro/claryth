"""CLI wrapper for the generalized PMDA top-20 database builder."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from top20_builder.build import main


if __name__ == "__main__":
    main()
