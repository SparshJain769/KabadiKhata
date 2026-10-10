"""Tests for the WhatsApp (Twilio sandbox) webhook adapter.

The adapter reuses the bot's channel-agnostic core (api_client/mock_api, cards,
strings_hi). These tests drive its pure helpers and its request handler with a
fake backend, so no real Twilio/network is needed — the live round-trip (ngrok +
a real WhatsApp message) is a manual step documented in the runbook.
"""
import base64

import pytest
from fastapi.testclient import TestClient

from bot import whatsapp_webhook as ww
from bot.strings_hi import MATERIAL_ORDER, material_label

PHOTO_BYTES = b"\xff\xd8\xff\xe0fake-jpeg-bytes"
RECEIPT = {
    "receipt_id": "KK-ABC123", "material": "PET", "weight_kg": 12.0,
    "price_inr_per_kg": 30.0, "total_inr": 360.0, "locality": "bawana",
    "ts": "2026-10-10T10:00:00+00:00", "hash": "abcdef1234567890", "synthetic": False,
}


class FakeApi:
    """Stand-in for bot.api_client with the same surface the adapter uses."""

    def __init__(self, collect_result):
        self._collect = collect_result
        self.registered = []
        self.last_payload = None

    def register(self, collector_id, name, locality=None):
        self.registered.append(collector_id)
        return {"actor_id": collector_id, "name": name}

    def collect(self, payload):
        self.last_payload = payload
        return self._collect

    def hisaab(self, collector_id):
        return {"collector_id": collector_id, "name": "", "month": "October",
                "month_kg": 10.0, "month_inr": 100.0, "count": 2,
                "today_kg": 2.0, "today_inr": 20.0, "chain_verified": True, "synthetic": False}


@pytest.fixture
def receipt_backend(monkeypatch, tmp_path):
    fake = FakeApi({"status": "receipt", "receipt": RECEIPT})
    monkeypatch.setattr(ww, "api", fake)
    monkeypatch.setattr(ww, "download_media", lambda url, content_type: PHOTO_BYTES)
    monkeypatch.setattr(ww, "PUBLIC_BASE_URL", "https://example.test")
    monkeypatch.setattr(ww, "CARD_DIR", tmp_path)
    ww.SESSIONS.clear()
    return fake


@pytest.fixture
def question_backend(monkeypatch, tmp_path):
    fake = FakeApi({"status": "question", "question_hi": "Taraazu 12 kg dikha raha hai, aapne 20 bola. Kaun sa sahi?"})
    monkeypatch.setattr(ww, "api", fake)
    monkeypatch.setattr(ww, "download_media", lambda url, content_type: PHOTO_BYTES)
    monkeypatch.setattr(ww, "PUBLIC_BASE_URL", "https://example.test")
    monkeypatch.setattr(ww, "CARD_DIR", tmp_path)
    ww.SESSIONS.clear()
    return fake


# ---- pure helpers ----
def test_collector_id_from_number():
    assert ww.collector_id_from_number("whatsapp:+919812345678") == "wa_919812345678"
    assert ww.collector_id_from_number("+919812345678") == "wa_919812345678"


def test_parse_material_choice():
    assert ww.parse_material_choice("1") == MATERIAL_ORDER[0]
    assert ww.parse_material_choice("3") == MATERIAL_ORDER[2]
    assert ww.parse_material_choice("0") is None
    assert ww.parse_material_choice("99") is None
    assert ww.parse_material_choice("hello") is None


def test_parse_weight():
    assert ww.parse_weight("12") == 12.0
    assert ww.parse_weight("12.5 kg") == 12.5
    assert ww.parse_weight("baara") is None
    assert ww.parse_weight("0") is None
    assert ww.parse_weight("600") is None


def test_material_menu_lists_every_material():
    menu = ww.material_menu()
    for i, m in enumerate(MATERIAL_ORDER, start=1):
        assert str(i) in menu and material_label(m) in menu


# ---- handler state machine (fake backend) ----
def _photo_form(frm="whatsapp:+919812345678"):
    return {"From": frm, "Body": "", "NumMedia": "1",
            "MediaUrl0": "https://api.twilio.com/media/abc", "MediaContentType0": "image/jpeg"}


def test_photo_prompts_for_material_and_opens_session(receipt_backend):
    reply = ww.handle_inbound(_photo_form())
    assert reply.get("media_url") is None
    assert material_label(MATERIAL_ORDER[0]) in reply["text"]
    assert ww.SESSIONS["wa_919812345678"]["state"] == "awaiting_material"
    assert receipt_backend.registered == ["wa_919812345678"]


def test_happy_path_photo_material_weight_returns_card(receipt_backend):
    ww.handle_inbound(_photo_form())
    ww.handle_inbound({"From": "whatsapp:+919812345678", "Body": "1", "NumMedia": "0"})
    reply = ww.handle_inbound({"From": "whatsapp:+919812345678", "Body": "12", "NumMedia": "0"})
    assert reply["media_url"].startswith("https://example.test/card/")
    assert reply["media_url"].endswith(".png")
    # the collection was sent with the tapped material + weight against the real contract
    assert receipt_backend.last_payload["taps"] == {"material": "PET", "kg": 12.0}
    assert receipt_backend.last_payload["collector_id"] == "wa_919812345678"
    assert "wa_919812345678" not in ww.SESSIONS  # session cleared after a receipt


def test_mismatch_returns_question_and_no_card(question_backend):
    ww.handle_inbound(_photo_form())
    ww.handle_inbound({"From": "whatsapp:+919812345678", "Body": "1", "NumMedia": "0"})
    reply = ww.handle_inbound({"From": "whatsapp:+919812345678", "Body": "20", "NumMedia": "0"})
    assert reply.get("media_url") is None
    assert "20 bola" in reply["text"]


def test_bad_weight_is_rejected_without_collecting(receipt_backend):
    ww.handle_inbound(_photo_form())
    ww.handle_inbound({"From": "whatsapp:+919812345678", "Body": "1", "NumMedia": "0"})
    reply = ww.handle_inbound({"From": "whatsapp:+919812345678", "Body": "nonsense", "NumMedia": "0"})
    assert reply.get("media_url") is None
    assert receipt_backend.last_payload is None  # never reached collect


def test_hisaab_keyword_returns_income_card(receipt_backend):
    reply = ww.handle_inbound({"From": "whatsapp:+919812345678", "Body": "hisaab", "NumMedia": "0"})
    assert reply["media_url"].startswith("https://example.test/card/")


# ---- TwiML + routes ----
def test_twiml_escapes_and_wraps():
    xml = ww.twiml(text="a & b <c>", media_url="https://x/y.png")
    assert "a &amp; b &lt;c&gt;" in xml
    assert "<Media>https://x/y.png</Media>" in xml
    assert xml.startswith("<?xml")


def test_webhook_route_and_card_serving(receipt_backend):
    client = TestClient(ww.app)
    client.post("/whatsapp", data=_photo_form())
    client.post("/whatsapp", data={"From": "whatsapp:+919812345678", "Body": "1", "NumMedia": "0"})
    r = client.post("/whatsapp", data={"From": "whatsapp:+919812345678", "Body": "12", "NumMedia": "0"})
    assert r.status_code == 200 and "<Media>" in r.text
    card_path = r.text.split("<Media>")[1].split("</Media>")[0]
    card_id = card_path.rsplit("/", 1)[1]  # e.g. <uuid>.png
    got = client.get(f"/card/{card_id}")
    assert got.status_code == 200 and got.headers["content-type"] == "image/png"
    assert got.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert client.get("/card/does-not-exist.png").status_code == 404
