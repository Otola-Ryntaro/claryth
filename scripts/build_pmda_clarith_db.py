"""CLI wrapper for building the PMDA clarithromycin candidate database."""

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pmda_builder.build import main


if __name__ == "__main__":
    main()

