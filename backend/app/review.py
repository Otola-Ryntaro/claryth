"""Shared clinical-review status contract for runtime datasets."""

CLINICALLY_REVIEWED_STATUS = "clinically_reviewed"


def is_clinically_reviewed(status: str | None) -> bool:
    return status == CLINICALLY_REVIEWED_STATUS

