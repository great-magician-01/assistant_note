"""Shared API types.

Snowflake IDs are 64-bit integers that exceed JavaScript's
``Number.MAX_SAFE_INTEGER`` (2^53). To prevent precision loss on the frontend,
all IDs are serialized as JSON strings at the API boundary.

``SnowflakeId`` accepts either an ``int`` or a ``str`` and always exposes the
value as a ``str``. Use it for every ``*_id`` field in request/response models.
"""

from typing import Optional

from pydantic import BeforeValidator
from typing_extensions import Annotated


def _coerce_to_str(v: object) -> object:
    """Coerce int (or str) IDs to str; pass None through unchanged."""
    if v is None:
        return None
    return str(v)


# A string-typed ID that accepts int input and converts it. Optional variant
# keeps None as None.
SnowflakeId = Annotated[str, BeforeValidator(_coerce_to_str)]
OptionalSnowflakeId = Annotated[Optional[str], BeforeValidator(_coerce_to_str)]
