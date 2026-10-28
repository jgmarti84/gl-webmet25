# database/radar_db/passwords.py
"""Password hashing and policy.

Single implementation shared by the API, db-init and the server CLI.
Argon2id via pwdlib, with the library's recommended parameters.
"""

from typing import Optional, Tuple

from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128

_hasher = PasswordHash.recommended()


class PasswordPolicyError(ValueError):
    """The password does not meet the policy."""


def hash_password(password: str) -> str:
    """Return the Argon2id hash of ``password`` (random salt, encoded string)."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Return True if ``password`` matches ``password_hash``; False otherwise."""
    try:
        return _hasher.verify(password, password_hash)
    except UnknownHashError:
        # Only an unknown/malformed stored hash counts as a failed verification
        # (pwdlib raises UnknownHashError for "", garbage and corrupt $argon2id$
        # strings). Anything else is a programming error and must propagate.
        return False


def verify_and_update(password: str, password_hash: str) -> Tuple[bool, Optional[str]]:
    """Verify and, if the hash uses outdated parameters, return a new hash."""
    try:
        return _hasher.verify_and_update(password, password_hash)
    except UnknownHashError:
        # Same reasoning as verify_password: only malformed hashes are swallowed.
        return False, None


def validate_password(password: str, username: str) -> None:
    if not isinstance(password, str) or not isinstance(username, str):
        raise PasswordPolicyError("La contraseña y el nombre de usuario deben ser texto")
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise PasswordPolicyError(
            f"La contraseña debe tener entre {MIN_PASSWORD_LENGTH} y " f"{MAX_PASSWORD_LENGTH} caracteres"
        )
    if not password.strip():
        raise PasswordPolicyError("La contraseña no puede estar formada solo por espacios")
    if password.strip().casefold() == username.strip().casefold():
        raise PasswordPolicyError("La contraseña no puede ser igual al nombre de usuario")


# Hash used to spend the same time when the user does not exist (timing attacks).
DUMMY_HASH = hash_password("timing-equalization-dummy-password")
