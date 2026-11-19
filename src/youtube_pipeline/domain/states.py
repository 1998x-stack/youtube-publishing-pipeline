"""Explicit state transition policy. Ambiguous upload outcomes fail closed."""
from enum import StrEnum


class State(StrEnum):
    QUEUED = "QUEUED"
    UPLOADING = "UPLOADING"
    UNKNOWN_UPLOAD_RESULT = "UNKNOWN_UPLOAD_RESULT"
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    DECORATING = "DECORATING"
    SCHEDULED = "SCHEDULED"
    PUBLISHED = "PUBLISHED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    FAILED_FINAL = "FAILED_FINAL"


ALLOWED = {
    State.QUEUED: {State.UPLOADING, State.NEEDS_REVIEW},
    State.UPLOADING: {State.UPLOADED, State.UNKNOWN_UPLOAD_RESULT, State.NEEDS_REVIEW},
    State.UPLOADED: {State.PROCESSING, State.DECORATING, State.NEEDS_REVIEW},
    State.PROCESSING: {State.PROCESSING, State.DECORATING, State.NEEDS_REVIEW},
    State.DECORATING: {State.SCHEDULED, State.NEEDS_REVIEW},
    State.SCHEDULED: {State.PUBLISHED, State.NEEDS_REVIEW},
    State.UNKNOWN_UPLOAD_RESULT: {State.NEEDS_REVIEW},
    State.NEEDS_REVIEW: {State.QUEUED, State.FAILED_FINAL},
    State.PUBLISHED: set(),
    State.FAILED_FINAL: set(),
}


def require_transition(before: State, after: State) -> None:
    if after not in ALLOWED[before]:
        raise ValueError(f"illegal state transition: {before} -> {after}")
