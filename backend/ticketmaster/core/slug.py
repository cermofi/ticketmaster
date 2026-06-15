from __future__ import annotations

import re
import secrets
import unicodedata


def strip_diacritics(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def slugify(value: str) -> str:
    text = unicodedata.normalize("NFC", value)
    text = strip_diacritics(text)
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text)
    text = text.strip("-")
    return text or secrets.token_hex(4)
