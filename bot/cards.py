"""Receipt card renderer for Kabadi Khata.

Produces a shareable PNG receipt card from a receipt dict (the shape returned by
POST /collections, see KABADI_KHATA_SCOPED_DOWN.md §3.1). Runs in the bot
process on the laptop (CLAUDE.md #3), not in Lambda.

    from bot.cards import make_receipt_card
    png_bytes = make_receipt_card(receipt)        # -> bytes, send via Telegram

Synthetic receipts (receipt["synthetic"] is True) get a diagonal "SYNTHETIC"
watermark and a footer line, per CLAUDE.md design rule 3.
"""
from __future__ import annotations

import io
import os
from datetime import datetime

import qrcode
from PIL import Image, ImageDraw, ImageFont

try:  # works whether imported as bot.cards or from inside bot/
    from bot.strings_hi import material_label
except ImportError:  # pragma: no cover
    from strings_hi import material_label

# --- palette ---
BG = (247, 248, 246)
CARD = (255, 255, 255)
INK = (28, 32, 30)
MUTED = (120, 128, 124)
GREEN = (29, 122, 72)
GREEN_DK = (18, 92, 54)
LINE = (224, 228, 224)

W, H = 640, 820
PAD = 36

# Fonts to try, in order. Bundled first (future), then common OS fonts.
_FONT_CANDIDATES = [
    os.path.join(os.path.dirname(__file__), "assets", "NotoSans-Regular.ttf"),
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial.ttf",
]
_FONT_CANDIDATES_BOLD = [
    os.path.join(os.path.dirname(__file__), "assets", "NotoSans-Bold.ttf"),
    r"C:\Windows\Fonts\segoeuib.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
]


def _resolve_font_path(bold: bool) -> str | None:
    for p in (_FONT_CANDIDATES_BOLD if bold else _FONT_CANDIDATES):
        if os.path.exists(p):
            return p
    return None


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = _resolve_font_path(bold)
    if path:
        return ImageFont.truetype(path, size)
    return ImageFont.load_default()  # last resort (bitmap, not scalable)


def _supports_rupee() -> bool:
    try:
        return _font(20).getmask("\u20B9").size != (0, 0)
    except Exception:
        return False


_RUPEE = "\u20B9" if _supports_rupee() else "Rs "


def _money(amount: float) -> str:
    return f"{_RUPEE}{amount:,.0f}"


def _fmt_ts(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%d %b %Y, %I:%M %p")
    except Exception:
        return str(ts)[:16]


def _qr(data: str, box: int = 4) -> Image.Image:
    qr = qrcode.QRCode(box_size=box, border=1)
    qr.add_data(data)
    qr.make(fit=True)
    return qr.make_image(fill_color=(28, 32, 30), back_color=(255, 255, 255)).convert("RGB")


def _watermark(size: tuple[int, int], text: str = "SYNTHETIC") -> Image.Image:
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    f = _font(44, bold=True)
    step = 230
    for y in range(-size[1], size[1] * 2, 120):
        for x in range(-size[0], size[0] * 2, step):
            d.text((x, y), text, font=f, fill=(150, 160, 150, 38))
    return layer.rotate(30, expand=False)


def make_receipt_card(receipt: dict) -> bytes:
    """Render a receipt dict to PNG bytes."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # card panel
    d.rounded_rectangle([16, 16, W - 16, H - 16], radius=22, fill=CARD, outline=LINE, width=2)

    # header band
    d.rounded_rectangle([16, 16, W - 16, 110], radius=22, fill=GREEN)
    d.rectangle([16, 70, W - 16, 110], fill=GREEN)  # square off the bottom of the band
    d.text((PAD, 34), "Kabadi Khata", font=_font(32, bold=True), fill=(255, 255, 255))
    d.text((PAD, 74), "Verified collection receipt", font=_font(16), fill=(223, 240, 230))

    y = 134
    rid = receipt.get("receipt_id", "KK-??????")
    d.text((PAD, y), rid, font=_font(30, bold=True), fill=INK)
    y += 48
    d.line([PAD, y, W - PAD, y], fill=LINE, width=2)
    y += 22

    # material + weight
    mat = material_label(receipt.get("material", "unknown"))
    kg = receipt.get("weight_kg", 0)
    d.text((PAD, y), "Maal", font=_font(16), fill=MUTED)
    d.text((PAD, y + 22), str(mat), font=_font(26, bold=True), fill=INK)
    d.text((W - PAD - 160, y), "Weight", font=_font(16), fill=MUTED)
    d.text((W - PAD - 160, y + 22), f"{kg:g} kg", font=_font(26, bold=True), fill=INK)
    y += 74

    # price block
    rate = receipt.get("price_inr_per_kg", 0)
    total = receipt.get("total_inr")
    if total is None:
        total = round(float(rate) * float(kg or 0), 2)
    d.rounded_rectangle([PAD, y, W - PAD, y + 92], radius=14, fill=(238, 247, 241))
    d.text((PAD + 18, y + 16), "Total (indicative)", font=_font(16), fill=GREEN_DK)
    d.text((PAD + 18, y + 40), _money(total), font=_font(40, bold=True), fill=GREEN_DK)
    d.text((W - PAD - 150, y + 36), f"@ {_money(rate)}/kg", font=_font(18), fill=GREEN_DK)
    y += 116

    # meta: locality + time
    loc = str(receipt.get("locality", "")).replace("_", " ").title()
    d.text((PAD, y), "Ilaaka", font=_font(15), fill=MUTED)
    d.text((PAD, y + 20), loc or "-", font=_font(20), fill=INK)
    d.text((W - PAD - 230, y), "Samay", font=_font(15), fill=MUTED)
    d.text((W - PAD - 230, y + 20), _fmt_ts(receipt.get("ts", "")), font=_font(18), fill=INK)
    y += 66

    # hash + chain + QR
    h = str(receipt.get("hash", ""))
    short = h[:12] if h else "-"
    d.line([PAD, y, W - PAD, y], fill=LINE, width=2)
    y += 18
    d.text((PAD, y), "Chain hash", font=_font(15), fill=MUTED)
    d.text((PAD, y + 20), short, font=_font(20, bold=True), fill=INK)
    # drawn checkmark (robust across fonts/OSes; U+2713 is tofu in some fonts)
    cy = y + 50
    d.line([(PAD, cy + 12), (PAD + 6, cy + 18)], fill=GREEN, width=3)
    d.line([(PAD + 6, cy + 18), (PAD + 17, cy + 5)], fill=GREEN, width=3)
    d.text((PAD + 26, cy), "chain verified", font=_font(17, bold=True), fill=GREEN)

    qr_img = _qr(f"KK:{rid}:{h}", box=4).resize((132, 132), Image.NEAREST)
    img.paste(qr_img, (W - PAD - 132, y))

    # synthetic treatment
    if receipt.get("synthetic", False):
        wm = _watermark((W, H))
        img = Image.alpha_composite(img.convert("RGBA"), wm).convert("RGB")
        d = ImageDraw.Draw(img)
        d.text((PAD, H - 50), "Demo data \u2014 asli collection nahi", font=_font(15), fill=MUTED)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def save_receipt_card(receipt: dict, path: str) -> str:
    with open(path, "wb") as f:
        f.write(make_receipt_card(receipt))
    return path
