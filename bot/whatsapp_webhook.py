"""WhatsApp transport adapter (Twilio Sandbox) for Kabadi Khata.

A thin FastAPI webhook that reuses the bot's channel-agnostic core — the same
``api_client`` (real backend), ``cards`` and ``strings_hi`` the Telegram bot uses.
Telegram is untouched; this is an additional channel for the demo.

Why a separate little server: Twilio delivers inbound WhatsApp messages as a
form POST to a public URL (ngrok in dev), and to send an image back it must
fetch it from a public URL — so we serve the generated card at ``/card/{id}``
through the same tunnel. Replies are TwiML in the webhook response (no outbound
REST call needed); the Twilio credentials are only used to download the inbound
photo, whose media URL is Basic-auth protected.

Flow (adapted for WhatsApp, which has no kg keypad): send a photo → reply with a
numbered material menu → user types a number → ask for the weight → user types
the kg → we call the real ``POST /collections``: on a pass, reply with the
receipt card; on a mismatch, reply with the agent's one Hindi question and write
nothing. Voice notes are still out of scope here (same as the bot).

Run (demo): point ngrok at this port, set the sandbox "when a message comes in"
webhook to ``https://<ngrok>/whatsapp``; see docs/whatsapp_runbook.md.
"""
from __future__ import annotations

import base64
import io
import logging
import os
import re
import uuid
from pathlib import Path
from xml.sax.saxutils import escape

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse

from bot.cards import make_hisaab_card, make_receipt_card
from bot.strings_hi import MATERIAL_ORDER, material_label, t

log = logging.getLogger("kk.whatsapp")

# Backend: real API when KK_USE_MOCK=0 (the demo), else the offline mock — same
# convention as the Telegram bot. Tests rebind ``api`` to a fake.
if os.environ.get("KK_USE_MOCK", "1") == "0":
    from bot import api_client as api  # noqa: F401  (chosen backend)
else:
    from bot import mock_api as api  # noqa: F401

# The public base URL Twilio can reach (the ngrok https address). Set in .env.
PUBLIC_BASE_URL = os.environ.get("WHATSAPP_PUBLIC_URL", "").rstrip("/")
# Where generated cards are written so /card/{id} can serve them to Twilio.
CARD_DIR = Path(os.environ.get("WHATSAPP_CARD_DIR", "data/wa_cards"))

# Per-sender conversation state (in-memory; fine for a single-process demo).
SESSIONS: dict[str, dict] = {}

_HISAAB_WORDS = {"hisaab", "mera hisaab", "/hisaab", "हिसाब", "मेरा हिसाब"}
_CARD_NAME = re.compile(r"[0-9a-f]+\.png")


def collector_id_from_number(whatsapp_from: str) -> str:
    """'whatsapp:+919812345678' -> 'wa_919812345678' (digits only, stable per phone)."""
    digits = re.sub(r"\D", "", whatsapp_from or "")
    return f"wa_{digits}"


def parse_material_choice(text: str) -> str | None:
    """A reply of '1'..'N' maps to MATERIAL_ORDER; anything else is None."""
    s = (text or "").strip()
    if s.isdigit():
        n = int(s)
        if 1 <= n <= len(MATERIAL_ORDER):
            return MATERIAL_ORDER[n - 1]
    return None


def parse_weight(text: str) -> float | None:
    """First number in the message as kg, if it is a sane weight (0 < kg <= 500)."""
    m = re.search(r"\d+(?:\.\d+)?", text or "")
    if not m:
        return None
    kg = float(m.group())
    return kg if 0 < kg <= 500 else None


def material_menu(lang: str = "hi") -> str:
    return "\n".join(f"{i}. {material_label(m, lang)}" for i, m in enumerate(MATERIAL_ORDER, start=1))


def twiml(text: str | None = None, media_url: str | None = None) -> str:
    """A minimal TwiML MessagingResponse (hand-built so we add no Twilio dependency)."""
    parts = ["<Message>"]
    if text:
        parts.append(f"<Body>{escape(text)}</Body>")
    if media_url:
        parts.append(f"<Media>{escape(media_url)}</Media>")
    parts.append("</Message>")
    return '<?xml version="1.0" encoding="UTF-8"?><Response>' + "".join(parts) + "</Response>"


def download_media(url: str, content_type: str) -> bytes:
    """Fetch a Twilio-hosted inbound media file (Basic-auth protected)."""
    sid, tok = os.environ.get("TWILIO_ACCOUNT_SID"), os.environ.get("TWILIO_AUTH_TOKEN")
    auth = (sid, tok) if sid and tok else None
    with httpx.Client(timeout=30) as c:
        resp = c.get(url, auth=auth, follow_redirects=True)
        resp.raise_for_status()
        return resp.content


def _resize_for_upload(data: bytes) -> bytes:
    """Resize to <=1024 px long side as JPEG (CLAUDE.md #3). On any failure, pass through."""
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        im.thumbnail((1024, 1024))
        if im.mode != "RGB":
            im = im.convert("RGB")
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    except Exception:
        return data


def _store_card(data: bytes) -> str:
    """Write card PNG bytes under CARD_DIR; return the filename served at /card/{id}."""
    CARD_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.png"
    (CARD_DIR / name).write_bytes(data)
    return name


def _card_url(name: str) -> str:
    return f"{PUBLIC_BASE_URL}/card/{name}"


def handle_inbound(form: dict) -> dict:
    """Core state machine: a Twilio inbound form -> {'text', 'media_url'} reply.

    Pure of HTTP/TwiML so it is unit-testable; the route wraps it as TwiML.
    """
    frm = form.get("From", "")
    cid = collector_id_from_number(frm)
    body = (form.get("Body") or "").strip()
    num_media = int(form.get("NumMedia", "0") or 0)

    # 1) A photo starts (or restarts) a collection.
    if num_media > 0 and str(form.get("MediaContentType0", "")).startswith("image"):
        try:
            api.register(cid, name=cid)
        except Exception as exc:  # registration is idempotent; don't block the flow
            log.warning("register failed for %s: %s", cid, exc)
        raw = download_media(form.get("MediaUrl0", ""), form.get("MediaContentType0", ""))
        photo_b64 = base64.b64encode(_resize_for_upload(raw)).decode()
        SESSIONS[cid] = {"state": "awaiting_material", "photo_b64": photo_b64, "locality": ""}
        return {"text": t("choose_material") + "\n" + material_menu()}

    # 2) "मेरा हिसाब" / hisaab -> income card.
    if body.lower() in _HISAAB_WORDS:
        data = dict(api.hisaab(cid))
        return {"text": t("hisaab_button"), "media_url": _card_url(_store_card(make_hisaab_card(data)))}

    sess = SESSIONS.get(cid)

    # 3) Expecting a material choice.
    if sess and sess["state"] == "awaiting_material":
        material = parse_material_choice(body)
        if material is None:
            return {"text": t("choose_material") + "\n" + material_menu()}
        sess["material"] = material
        sess["state"] = "awaiting_weight"
        return {"text": t("enter_weight")}

    # 4) Expecting a weight -> run the real collection.
    if sess and sess["state"] == "awaiting_weight":
        kg = parse_weight(body)
        if kg is None:
            return {"text": t("bad_weight")}
        resp = api.collect({
            "collector_id": cid,
            "photo_b64": sess["photo_b64"],
            "taps": {"material": sess["material"], "kg": kg},
            "locality": sess.get("locality", ""),
        })
        SESSIONS.pop(cid, None)
        if resp.get("status") == "receipt":
            card = make_receipt_card(resp["receipt"])
            return {"text": t("receipt_ready"), "media_url": _card_url(_store_card(card))}
        return {"text": t("question_prefix") + resp.get("question_hi", "")}

    # 5) Anything else: greet and ask for a photo.
    return {"text": t("welcome") + "\n\n" + t("send_photo")}


app = FastAPI(title="Kabadi Khata — WhatsApp webhook")


@app.get("/health")
def health() -> dict:
    return {"ok": True, "public_base_url": PUBLIC_BASE_URL or None}


@app.post("/whatsapp")
async def whatsapp(request: Request) -> Response:
    form = {k: str(v) for k, v in (await request.form()).items()}
    reply = handle_inbound(form)
    return Response(content=twiml(reply.get("text"), reply.get("media_url")), media_type="application/xml")


@app.get("/card/{card_id}")
def card(card_id: str) -> FileResponse:
    if not _CARD_NAME.fullmatch(card_id):
        raise HTTPException(404, "no such card")
    path = CARD_DIR / card_id
    if not path.exists():
        raise HTTPException(404, "no such card")
    return FileResponse(path, media_type="image/png")
