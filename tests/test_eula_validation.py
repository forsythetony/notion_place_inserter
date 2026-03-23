"""Tests for EULA plain-language summary validation and SHA-256 helper."""

import pytest

from app.services.eula_validation import (
    compute_content_sha256,
    validate_plain_language_summary,
)


def test_compute_content_sha256_utf8():
    h = compute_content_sha256("hello")
    assert len(h) == 64
    assert h == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"


def test_validate_plain_language_summary_ok():
    d = validate_plain_language_summary(
        {
            "dos": ["a"],
            "donts": ["b"],
            "cautions": ["c"],
        }
    )
    assert d == {"dos": ["a"], "donts": ["b"], "cautions": ["c"]}


def test_validate_plain_language_summary_strips_strings():
    d = validate_plain_language_summary(
        {
            "dos": ["  x  "],
            "donts": ["y"],
            "cautions": ["z"],
        }
    )
    assert d["dos"] == ["x"]


@pytest.mark.parametrize(
    "bad",
    [
        None,
        [],
        {"dos": ["a"], "donts": ["b"]},
        {"dos": ["a"], "donts": ["b"], "cautions": [], "extra": []},
        {"dos": [""], "donts": ["b"], "cautions": ["c"]},
    ],
)
def test_validate_plain_language_summary_rejects(bad):
    with pytest.raises(ValueError):
        validate_plain_language_summary(bad)
