"""Normalize recipient addresses to the form Sendblue matches on."""

import re

# Calling codes for countries we can expand national numbers from.
COUNTRY_CALLING_CODES = {
    "AU": "61",
    "CA": "1",
    "CN": "86",
    "DE": "49",
    "FR": "33",
    "GB": "44",
    "JP": "81",
    "KR": "82",
    "TW": "886",
    "US": "1",
}
# Countries whose national numbers start with a trunk "0" that E.164 drops.
# Sendblue treats "+82010..." and "+8210..." as different contacts.
TRUNK_ZERO_CODES = {"33", "44", "49", "61", "81", "82", "86", "886"}

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SEPARATORS = re.compile(r"[\s\-().]")


def normalize_address(raw: str, country: str | None) -> str:
    """Return an E.164 number or a lowercased email, or raise ValueError."""
    value = raw.strip()
    if "@" in value:
        if not _EMAIL.match(value):
            raise ValueError("invalid email address")
        return value.lower()

    value = _SEPARATORS.sub("", value)
    if value.startswith("00"):
        value = "+" + value[2:]

    if value.startswith("+"):
        digits = value[1:]
        if not digits.isdigit():
            raise ValueError("invalid phone number")
        digits = _drop_trunk_zero(digits)
    else:
        if not value.isdigit():
            raise ValueError("invalid phone number")
        code = COUNTRY_CALLING_CODES.get(country or "")
        if code is None:
            raise ValueError("cannot expand a national number for this country")
        if code == "1" and len(value) == 11 and value.startswith("1"):
            value = value[1:]
        elif code in TRUNK_ZERO_CODES:
            value = value.removeprefix("0")
        digits = code + value

    if not 8 <= len(digits) <= 15:
        raise ValueError("invalid phone number length")
    return "+" + digits


def _drop_trunk_zero(digits: str) -> str:
    for code in sorted(TRUNK_ZERO_CODES, key=len, reverse=True):
        if digits.startswith(code + "0"):
            return code + digits[len(code) + 1 :]
    return digits
