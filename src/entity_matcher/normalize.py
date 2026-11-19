"""Name normalisation for product matching.

The goal is to make two names that refer to the same product compare equal,
while keeping every digit that changes *what* the product is.

Two rules matter more than the rest:

1. Packaging is not identity. "Laptop Charger 65W - box of 10" and
   "laptop charger 65W (pack 20)" are the same product sold in two pack sizes,
   so packaging words and their quantities are removed before comparing.
2. Spec numbers are identity. "Memory DDR4 16GB" and "Memory DDR4 32GB" look
   very alike as strings, but they are different products. Numbers are
   therefore extracted separately and compared exactly
   (see :func:`extract_numbers` and the numeric guard in ``matcher``).
"""

from __future__ import annotations

import re
import unicodedata

# Words that describe the package, not the product.
PACKAGING_WORDS = frozenset(
    {
        "BOX", "BOXES", "PACK", "PK", "CARTON", "CASE", "BULK", "PALLET", "BAG",
        "BLISTER", "RETAIL", "PCS", "PC", "UN", "UNITS", "OF",
        "CAIXA", "PACOTE", "UNIDADES",
    }
)

# "box of 10", "pack 20", "carton 24", "caixa 10"
_PACKAGE_OF = re.compile(
    r"\b(?:BOX|PACK|PK|CARTON|CASE|BAG|CAIXA|PACOTE)\s*(?:OF\s*)?\d+\b"
)
# "50 pcs", "10 un", "12 units", "3 pack"
_QTY_UNIT = re.compile(r"\b\d+\s*(?:PCS|PC|UN|UNITS|UNIDADES|PACK|PK)\b")

# Spec units glued to their number so "16 GB" and "16GB" agree.
_SPEC_UNITS = ("GB", "TB", "MB", "IN", "MHZ", "GHZ", "HZ", "W", "MM", "M", "V", "MAH")

# Common abbreviations normalised to one spelling.
SYNONYMS = {
    "MEM": "MEMORY",
    "CHG": "CHARGER",
    "CHRG": "CHARGER",
    "CBL": "CABLE",
    "NET": "NETWORK",
    "WRLS": "WIRELESS",
    "MON": "MONITOR",
    "NTBK": "NOTEBOOK",
}

_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def strip_accents(text: str) -> str:
    """Remove diacritics: 'Memória Câmera' -> 'Memoria Camera'."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _base(text: str) -> str:
    text = strip_accents(text).upper()
    # decimal comma -> decimal point, so "23,8" and "23.8" agree
    text = re.sub(r"(\d),(\d)", r"\1.\2", text)
    # glue spec units like "16 GB" -> "16GB" so they stay one token
    text = re.sub(r"(\d)\s+(" + "|".join(_SPEC_UNITS) + r")\b", r"\1\2", text)
    return text


def _drop_packaging(text: str) -> str:
    text = _PACKAGE_OF.sub(" ", text)
    text = _QTY_UNIT.sub(" ", text)
    tokens = [t for t in re.split(r"[^A-Z0-9.%]+", text) if t]
    return " ".join(t for t in tokens if t not in PACKAGING_WORDS)


def normalize(name: str) -> str:
    """Return the comparison key for a product name.

    >>> normalize("Memória DDR4 16 GB - Caixa 10 un")
    'MEMORIA DDR4 16GB'
    >>> normalize("laptop charger 65W (box of 10)")
    'LAPTOP CHARGER 65W'
    """
    text = _drop_packaging(_base(name))
    tokens = [t.rstrip(".") for t in text.split()]  # "Mem." -> "MEM"
    tokens = [SYNONYMS.get(t, t) for t in tokens if t]
    return " ".join(tokens).strip(" .")


def extract_numbers(name: str) -> tuple[str, ...]:
    """Return the spec numbers of a name, sorted, packaging quantities excluded.

    >>> extract_numbers("Laptop Charger 65W - box of 10")
    ('65',)
    >>> extract_numbers("Monitor 23,8in pack 2")
    ('23.8',)
    """
    text = _drop_packaging(_base(name))
    nums = []
    for raw in _NUMBER.findall(text):
        n = raw.rstrip("0").rstrip(".") if "." in raw else raw.lstrip("0") or "0"
        nums.append(n)
    return tuple(sorted(nums))
