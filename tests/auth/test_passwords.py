# tests/auth/test_passwords.py
import pytest
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from radar_db.passwords import (
    DUMMY_HASH,
    PasswordPolicyError,
    hash_password,
    validate_password,
    verify_and_update,
    verify_password,
)


def test_hash_is_not_plaintext_and_verifies():
    hashed = hash_password("correct-horse-battery")
    assert hashed != "correct-horse-battery"
    assert hashed.startswith("$argon2id$")
    assert verify_password("correct-horse-battery", hashed)


def test_wrong_password_does_not_verify():
    hashed = hash_password("correct-horse-battery")
    assert not verify_password("wrong-password-123", hashed)


def test_malformed_hash_returns_false_instead_of_raising():
    assert not verify_password("anything", "not-a-real-hash")


def test_verify_and_update_returns_no_new_hash_for_current_params():
    hashed = hash_password("correct-horse-battery")
    ok, new_hash = verify_and_update("correct-horse-battery", hashed)
    assert ok is True
    assert new_hash is None


def test_dummy_hash_is_a_valid_hash():
    assert DUMMY_HASH.startswith("$argon2id$")
    assert not verify_password("whatever", DUMMY_HASH)


@pytest.mark.parametrize("password", ["short", "a" * 11, "x" * 129])
def test_policy_rejects_bad_length(password):
    with pytest.raises(PasswordPolicyError):
        validate_password(password, username="alice")


def test_policy_rejects_password_equal_to_username():
    with pytest.raises(PasswordPolicyError):
        validate_password("alice.the.admin", username="Alice.The.Admin")


def test_policy_accepts_long_password():
    validate_password("correct-horse-battery", username="alice")


def test_same_password_hashes_differently_and_both_verify():
    first = hash_password("correct-horse-battery")
    second = hash_password("correct-horse-battery")
    assert first != second
    assert verify_password("correct-horse-battery", first)
    assert verify_password("correct-horse-battery", second)


def test_verify_and_update_rehashes_weaker_parameters():
    weak = PasswordHash((Argon2Hasher(time_cost=1, memory_cost=8, parallelism=1),)).hash("correct-horse-battery")
    ok, new_hash = verify_and_update("correct-horse-battery", weak)
    assert ok is True
    assert new_hash is not None
    assert new_hash != weak
    assert verify_password("correct-horse-battery", new_hash)


@pytest.mark.parametrize("password", ["a" * 12, "a" * 128])
def test_policy_accepts_boundary_lengths(password):
    validate_password(password, username="alice")


def test_policy_rejects_whitespace_only_password():
    with pytest.raises(PasswordPolicyError):
        validate_password(" " * 12, username="alice")


@pytest.mark.parametrize("bad_hash", ["not-a-real-hash", "$argon2id$garbage", ""])
def test_corrupt_hashes_fail_verification_without_raising(bad_hash):
    assert verify_password("anything", bad_hash) is False
    assert verify_and_update("anything", bad_hash) == (False, None)


@pytest.mark.parametrize(
    "password, username",
    [(None, "alice"), (123456789012, "alice"), ("correct-horse-battery", None)],
)
def test_policy_rejects_non_string_arguments(password, username):
    with pytest.raises(PasswordPolicyError):
        validate_password(password, username=username)


def test_policy_username_comparison_is_casefolded():
    with pytest.raises(PasswordPolicyError):
        validate_password("straße-straße", username="STRASSE-STRASSE")
