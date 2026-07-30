"""Reusable field types for input the storage or serialization layer cannot survive.

Both live here rather than in one module's schemas because the same values arrive
through several modules (ticket bodies, comments, tags, the search query, saved
view filters, notification preferences).
"""

from typing import Annotated, Any

from pydantic import AfterValidator, EmailStr

MAX_JSON_DEPTH = 8  # generous for a filter set; deeper is a client bug, not a use case


def _no_nul(value: str) -> str:
    # Postgres text columns cannot store U+0000; asyncpg raises on INSERT
    if "\x00" in value:
        raise ValueError("must not contain NUL bytes")
    return value


def _bounded_depth(value: Any, depth: int = 0) -> Any:
    if depth > MAX_JSON_DEPTH:
        raise ValueError(f"must not nest more than {MAX_JSON_DEPTH} levels deep")
    if isinstance(value, dict):
        for item in value.values():
            _bounded_depth(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _bounded_depth(item, depth + 1)
    return value


def _normalise_email(value: str) -> str:
    # One mailbox, one account: mail domains are case-insensitive and every
    # mainstream provider treats the local part that way too.
    return value.strip().lower()


SafeText = Annotated[str, AfterValidator(_no_nul)]
BoundedJson = Annotated[dict, AfterValidator(_bounded_depth)]
NormalisedEmail = Annotated[EmailStr, AfterValidator(_normalise_email)]
