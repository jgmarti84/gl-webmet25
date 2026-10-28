# api/app/schemas/text.py
"""Base for the public request bodies: text PostgreSQL cannot store is refused up front (422)."""

from pydantic import BaseModel, field_validator


class StrictText(BaseModel):
    """Rejects, in every text field of the body, characters that would otherwise end in a 500.

    PostgreSQL cannot store the null character ("\\x00") and its driver raises an error if one reaches a query;
    a lone surrogate (not valid UTF-8) does the same. These fields are public, so anyone can send them.
    """

    # "*" runs the check on every field of the model, including the ones of subclasses; "before" runs it on
    # the raw value, ahead of the length and format rules.
    @field_validator("*", mode="before")
    @classmethod
    def _storable_text(cls, value):
        if isinstance(value, str):
            if "\x00" in value:
                raise ValueError("Carácter no permitido")
            try:
                value.encode("utf-8")
            except UnicodeEncodeError:
                raise ValueError("Carácter no permitido")
        return value
