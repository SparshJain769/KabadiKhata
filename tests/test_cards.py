"""Tests for the receipt card renderer."""
import io
import pathlib
import sys

from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from bot.cards import make_receipt_card  # noqa: E402

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _receipt(**kw):
    base = {
        "receipt_id": "KK-7F3A2C",
        "material": "PET",
        "weight_kg": 12.0,
        "price_inr_per_kg": 10,
        "total_inr": 120.0,
        "locality": "lajpat_nagar",
        "ts": "2026-10-09T10:15:00+00:00",
        "hash": "9a8b7c6d5e4f3a2b1c0d",
        "synthetic": True,
    }
    base.update(kw)
    return base


def test_returns_valid_png_of_expected_size():
    data = make_receipt_card(_receipt())
    assert data[:8] == PNG_MAGIC
    assert Image.open(io.BytesIO(data)).size == (640, 820)


def test_handles_missing_total_inr():
    r = _receipt()
    r.pop("total_inr")
    assert Image.open(io.BytesIO(make_receipt_card(r))).size == (640, 820)


def test_non_synthetic_receipt_renders():
    assert Image.open(io.BytesIO(make_receipt_card(_receipt(synthetic=False)))).size == (640, 820)


def test_unknown_material_does_not_crash():
    assert make_receipt_card(_receipt(material="unknown"))[:8] == PNG_MAGIC
