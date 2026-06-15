from __future__ import annotations

import re

import pytest

from ticketmaster.core.slug import slugify
from ticketmaster.services import admin


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("ICZ -> MFČR", "icz-mfcr"),
        ("Městská část Praha", "mestska-cast-praha"),
        ("Česká spořitelna", "ceska-sporitelna"),
        ("Žďár nad Sázavou", "zdar-nad-sazavou"),
        ("Příliš žluťoučký kůň", "prilis-zlutoucky-kun"),
        ("foo---bar", "foo-bar"),
        ("a / b // c", "a-b-c"),
        ("--hello--", "hello"),
        ("  spaced  ", "spaced"),
    ],
)
def test_slugify(value: str, expected: str) -> None:
    assert slugify(value) == expected


def test_slugify_empty_input_uses_fallback() -> None:
    assert re.fullmatch(r"[a-f0-9]{8}", slugify("---"))


def test_create_partner_and_client_keys_with_czech_diacritics(db) -> None:
    partner = admin.create_partner(db, name="ICZ", source="test")
    assert partner.key == "icz"

    client = admin.create_client(db, partner_key_or_id=partner.id, name="MFČR", source="test")
    assert client.key == "icz-mfcr"


def test_create_partner_duplicate_key_gets_numeric_suffix(db) -> None:
    first = admin.create_partner(db, name="Partner A", source="test")
    second = admin.create_partner(db, name="Partner A", source="test")

    assert first.key == "partner-a"
    assert second.key == "partner-a-2"


def test_create_client_duplicate_key_gets_numeric_suffix(db) -> None:
    partner = admin.create_partner(db, name="Partner A", source="test")
    first = admin.create_client(db, partner_key_or_id=partner.id, name="Client A", source="test")
    second = admin.create_client(db, partner_key_or_id=partner.id, name="Client A", source="test")

    assert first.key == "partner-a-client-a"
    assert second.key == "partner-a-client-a-2"
