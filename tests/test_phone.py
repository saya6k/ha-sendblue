"""Tests for recipient address normalization."""

import pytest

from custom_components.sendblue.phone import normalize_address


@pytest.mark.parametrize(
    ("raw", "country", "expected"),
    [
        ("010-1234-5678", "KR", "+821012345678"),
        ("01012345678", "KR", "+821012345678"),
        ("+82 10 1234 5678", "KR", "+821012345678"),
        ("+82-010-1234-5678", "KR", "+821012345678"),
        ("+8201012345678", "US", "+821012345678"),
        ("0082 10 1234 5678", "US", "+821012345678"),
        ("(555) 123-4567", "US", "+15551234567"),
        ("1 555 123 4567", "US", "+15551234567"),
        ("+1 (555) 123-4567", "KR", "+15551234567"),
        ("090-1234-5678", "JP", "+819012345678"),
    ],
)
def test_phone_numbers_are_normalized_to_e164(raw, country, expected) -> None:
    assert normalize_address(raw, country) == expected


def test_email_is_trimmed_and_lowercased() -> None:
    assert normalize_address("  Mom@iCloud.com ", "KR") == "mom@icloud.com"


@pytest.mark.parametrize(
    ("raw", "country"),
    [
        ("", "KR"),
        ("not a number", "KR"),
        ("1234", "KR"),
        ("+12345678901234567", "KR"),
        ("mom@", "KR"),
        ("010-1234-5678", None),
        ("010-1234-5678", "ZZ"),
    ],
)
def test_invalid_input_raises_value_error(raw, country) -> None:
    with pytest.raises(ValueError):
        normalize_address(raw, country)
