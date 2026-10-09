"""Kabadi Khata Telegram bot (P4 skeleton, built against the mock API).

Run:  python -m bot.telegram_bot   (needs TELEGRAM_BOT_TOKEN in env or repo-root .env)

Mock -> real swap point: every backend call goes through the module-level
``api`` object (``import bot.mock_api as api``). Replacing that one import with
the real HTTP client is the whole swap. NOTE: when the real client is sync HTTP,
wrap its calls in ``asyncio.to_thread(...)``; the mock is fast and sync, so it
is called directly.

/demo toggles ``simulate_mismatch``: the NEXT collection returns the mismatch
question (no receipt written), then the flag clears itself so "dobara batao"
does not loop.

Conversation state is a manual state machine in ``context.user_data`` (no
ConversationHandler): need_name -> need_locality -> ready -> choosing_material
-> entering_kg -> (ready | awaiting_answer).
"""
from __future__ import annotations

import base64
import functools
import io
import json
import logging
import os
import re
import sys
from pathlib import Path

from PIL import Image
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
import bot.mock_api as api  # <- the swap point (see module docstring)
from bot.cards import make_hisaab_card, make_receipt_card
from bot.strings_hi import MATERIAL_ORDER, material_label, t

logging.basicConfig(format="%(asctime)s %(name)s %(levelname)s %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)  # httpx URLs contain the bot token
log = logging.getLogger("kabadi.bot")

REPO_ROOT = Path(__file__).resolve().parent.parent
LOCALITIES = json.loads((REPO_ROOT / "data" / "localities.json").read_text(encoding="utf-8"))["localities"]
KEYPAD_ROWS = [["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"], [".", "0", "back"]]
MAX_BUF = 6
_KG_RE = re.compile(r"^\d+(\.\d+)?$")


# --------------------------------------------------------------------------
# Pure, testable helpers
# --------------------------------------------------------------------------
def apply_keypad(buf: str, key: str) -> str:
    """Reducer for the kg keypad. Total and deterministic."""
    if key == "back":
        return buf[:-1]
    if key == ".":
        if "." in buf or len(buf) >= MAX_BUF:
            return buf
        return "0." if not buf else buf + "."
    if len(key) == 1 and key in "0123456789":
        return buf if len(buf) >= MAX_BUF else buf + key
    return buf


def parse_kg(buf: str) -> float | None:
    """Validated weight in kg, or None. Accepts 0 < kg <= 500."""
    if not isinstance(buf, str) or not _KG_RE.match(buf):
        return None
    v = float(buf)
    return v if 0 < v <= 500 else None


def build_payload(user_id, locality, material, kg, simulate, photo_b64=None) -> dict:
    return {
        "collector_id": "kab_" + str(user_id),
        "locality": locality,
        "taps": {"material": material, "kg": float(kg)},
        "photo_b64": photo_b64,
        "simulate": "mismatch" if simulate else None,
    }


def resize_for_upload(raw: bytes, max_side: int = 1024) -> bytes:
    """Resize so the long side <= max_side, re-encode as RGB JPEG."""
    img = Image.open(io.BytesIO(raw))
    if img.mode != "RGB":
        img = img.convert("RGB")
    w, h = img.size
    long_side = max(w, h)
    if long_side > max_side:
        scale = max_side / long_side
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85)
    return out.getvalue()


def locality_keyboard() -> InlineKeyboardMarkup:
    btns = [InlineKeyboardButton(l["name"], callback_data="loc:" + l["id"]) for l in LOCALITIES]
    return InlineKeyboardMarkup([btns[i:i + 2] for i in range(0, len(btns), 2)])


def material_keyboard() -> InlineKeyboardMarkup:
    btns = [InlineKeyboardButton(material_label(c), callback_data="mat:" + c) for c in MATERIAL_ORDER]
    return InlineKeyboardMarkup([btns[i:i + 2] for i in range(0, len(btns), 2)])


def kg_keyboard() -> InlineKeyboardMarkup:
    label = {"back": "⌫"}
    rows = [[InlineKeyboardButton(label.get(k, k), callback_data="kg:" + k) for k in row] for row in KEYPAD_ROWS]
    rows.append([InlineKeyboardButton("OK", callback_data="kg:ok")])
    return InlineKeyboardMarkup(rows)


def retry_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(t("btn_retry"), callback_data="again")]])


def load_env(path) -> None:
    """Tiny .env loader: KEY=VALUE lines, '#' comments, BOM-safe; never overrides real env."""
    p = Path(path)
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


# --------------------------------------------------------------------------
# State helpers
# --------------------------------------------------------------------------
def _registered(ud: dict) -> bool:
    return bool(ud.get("name") and ud.get("locality"))


def _reset_pending(ud: dict) -> None:
    ud["pending"] = {"material": None, "kg_buf": "", "photo_b64": None}


def _set_state(ud: dict, state: str) -> None:
    log.info("state %s -> %s", ud.get("state"), state)
    ud["state"] = state


def _locality_name(loc_id: str) -> str:
    for l in LOCALITIES:
        if l["id"] == loc_id:
            return l["name"]
    return loc_id


def safe(fn):
    """Handler wrapper: an exception replies error_generic and logs; never crashes the bot."""
    @functools.wraps(fn)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            await fn(update, context)
        except Exception:
            log.exception("handler %s failed", fn.__name__)
            msg = update.effective_message
            if msg is not None:
                try:
                    await msg.reply_text(t("error_generic"))
                except Exception:
                    log.exception("could not send error reply")
    return wrapper


async def _route_to_registration(msg, ud: dict) -> None:
    """Reply need_start and put the user at the right registration step."""
    await msg.reply_text(t("need_start"))
    if not ud.get("name"):
        _set_state(ud, "need_name")
        await msg.reply_text(t("ask_name"))
    else:
        _set_state(ud, "need_locality")
        await msg.reply_text(t("ask_locality"), reply_markup=locality_keyboard())


# --------------------------------------------------------------------------
# Command handlers
# --------------------------------------------------------------------------
@safe
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud, msg = context.user_data, update.effective_message
    ud.setdefault("pending", {"material": None, "kg_buf": "", "photo_b64": None})
    await msg.reply_text(t("welcome"), parse_mode=ParseMode.MARKDOWN)
    if not ud.get("name"):
        _set_state(ud, "need_name")
        await msg.reply_text(t("ask_name"))
    elif not ud.get("locality"):
        _set_state(ud, "need_locality")
        await msg.reply_text(t("ask_locality"), reply_markup=locality_keyboard())
    else:
        _set_state(ud, "ready")
        await msg.reply_text(t("send_photo"))


@safe
async def hisaab_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud, msg = context.user_data, update.effective_message
    if not _registered(ud):
        await msg.reply_text(t("need_start"))
        return
    r = dict(api.hisaab("kab_" + str(update.effective_user.id)))
    r["name"] = ud["name"]  # override the mock's hardcoded name with the registered name
    await msg.reply_photo(photo=make_hisaab_card(r), caption=t("hisaab_button"))


@safe
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(t("help"))


@safe
async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud, msg = context.user_data, update.effective_message
    _reset_pending(ud)
    await msg.reply_text(t("cancelled"))
    if _registered(ud):
        _set_state(ud, "ready")
    elif not ud.get("name"):
        _set_state(ud, "need_name")
        await msg.reply_text(t("ask_name"))
    else:
        _set_state(ud, "need_locality")
        await msg.reply_text(t("ask_locality"), reply_markup=locality_keyboard())


@safe
async def demo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud = context.user_data
    ud["simulate_mismatch"] = not ud.get("simulate_mismatch", False)
    await update.effective_message.reply_text(t("demo_on" if ud["simulate_mismatch"] else "demo_off"))


# --------------------------------------------------------------------------
# Message handlers
# --------------------------------------------------------------------------
@safe
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud, msg = context.user_data, update.effective_message
    if ud.get("state") == "need_name":
        name = (msg.text or "").strip()[:50]
        if not name:
            await msg.reply_text(t("ask_name"))
            return
        ud["name"] = name
        await msg.reply_text(t("name_saved", name=name))  # plain text, no parse_mode
        _set_state(ud, "need_locality")
        await msg.reply_text(t("ask_locality"), reply_markup=locality_keyboard())
    else:
        await msg.reply_text(t("help"))


@safe
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud, msg = context.user_data, update.effective_message
    if not _registered(ud):
        await msg.reply_text(t("need_start"))
        return
    gid = getattr(msg, "media_group_id", None)
    if gid is not None and ud.get("last_media_group_id") == gid:
        return  # album: only the first photo counts
    ud["last_media_group_id"] = gid

    photo_b64 = None
    try:
        f = await msg.photo[-1].get_file()
        raw = bytes(await f.download_as_bytearray())
        photo_b64 = base64.b64encode(resize_for_upload(raw)).decode("ascii")
    except Exception:
        log.warning("photo download/resize failed; continuing without photo", exc_info=True)

    _reset_pending(ud)
    ud["pending"]["photo_b64"] = photo_b64
    _set_state(ud, "choosing_material")
    await msg.reply_text(t("after_photo"))
    await msg.reply_text(t("choose_material"), reply_markup=material_keyboard())


@safe
async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    await msg.reply_text(t("voice_soon"))
    state = context.user_data.get("state")
    if state == "choosing_material":
        await msg.reply_text(t("choose_material"), reply_markup=material_keyboard())
    elif state == "entering_kg":
        await msg.reply_text(t("enter_weight"), reply_markup=kg_keyboard())


# --------------------------------------------------------------------------
# Callback handlers
# --------------------------------------------------------------------------
@safe
async def locality_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ud, msg = context.user_data, update.effective_message
    if not ud.get("name"):
        await _route_to_registration(msg, ud)
        return
    loc_id = query.data.split(":", 1)[1]
    if loc_id not in {l["id"] for l in LOCALITIES}:
        return
    ud["locality"] = loc_id
    await msg.reply_text(t("locality_saved", locality=_locality_name(loc_id)))
    _set_state(ud, "ready")
    _reset_pending(ud)
    await msg.reply_text(t("send_photo"))
    await msg.reply_text(t("help"))


@safe
async def material_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ud, msg = context.user_data, update.effective_message
    if not _registered(ud):
        await _route_to_registration(msg, ud)
        return
    code = query.data.split(":", 1)[1]
    if ud.get("state") != "choosing_material" or code not in MATERIAL_ORDER:
        return  # stale button
    ud.setdefault("pending", {})
    ud["pending"]["material"] = code
    ud["pending"]["kg_buf"] = ""
    _set_state(ud, "entering_kg")
    await msg.reply_text(
        t("enter_weight") + "\n" + t("weight_prompt", kg="0"), reply_markup=kg_keyboard()
    )


@safe
async def keypad_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ud, msg = context.user_data, update.effective_message
    if not _registered(ud):
        await _route_to_registration(msg, ud)
        return
    if ud.get("state") != "entering_kg":
        return  # stale button
    key = query.data.split(":", 1)[1]
    pending = ud["pending"]

    if key == "ok":
        kg = parse_kg(pending.get("kg_buf", ""))
        if kg is None:
            await msg.reply_text(t("bad_weight"))
            return
        await _do_collect(update, ud, kg)
        return

    old = pending.get("kg_buf", "")
    new = apply_keypad(old, key)
    if new == old:
        return
    pending["kg_buf"] = new
    try:
        await query.edit_message_text(
            t("enter_weight") + "\n" + t("weight_prompt", kg=new or "0"),
            reply_markup=kg_keyboard(),
        )
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            raise


async def _do_collect(update: Update, ud: dict, kg: float) -> None:
    msg = update.effective_message
    pending = ud["pending"]
    simulate = ud.get("simulate_mismatch", False)
    if simulate:
        ud["simulate_mismatch"] = False  # fire once
    payload = build_payload(
        update.effective_user.id, ud["locality"], pending["material"], kg, simulate,
        pending.get("photo_b64"),
    )
    await msg.reply_text(t("processing"))
    try:
        resp = api.collect(payload)  # real client: await asyncio.to_thread(api.collect, payload)
        status = resp.get("status")
        if status == "receipt":
            card = make_receipt_card(resp["receipt"])
            await msg.reply_photo(
                photo=card, caption=t("receipt_ready") + "\n" + t("synthetic_notice")
            )
            _reset_pending(ud)
            _set_state(ud, "ready")
        elif status == "question":
            await msg.reply_text(t("question_prefix") + resp["question_hi"], reply_markup=retry_keyboard())
            _set_state(ud, "awaiting_answer")
        else:
            raise ValueError("unknown collect status: %r" % (status,))
    except Exception:
        log.exception("collect failed")
        _reset_pending(ud)
        _set_state(ud, "ready")
        await msg.reply_text(t("error_generic"))


@safe
async def again_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ud, msg = context.user_data, update.effective_message
    if not _registered(ud):
        await _route_to_registration(msg, ud)
        return
    if ud.get("state") != "awaiting_answer":
        return  # stale button
    photo_b64 = ud.get("pending", {}).get("photo_b64")
    _reset_pending(ud)
    ud["pending"]["photo_b64"] = photo_b64
    _set_state(ud, "choosing_material")
    await msg.reply_text(t("choose_material"), reply_markup=material_keyboard())


async def error_handler(update, context: ContextTypes.DEFAULT_TYPE):
    log.error("unhandled error", exc_info=context.error)
    msg = getattr(update, "effective_message", None)
    if msg is not None:
        try:
            await msg.reply_text(t("error_generic"))
        except Exception:
            pass


def main() -> None:
    load_env(REPO_ROOT / ".env")
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("TELEGRAM_BOT_TOKEN is not set. Put it in the repo-root .env or the environment.")
        sys.exit(1)
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("hisaab", hisaab_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))
    app.add_handler(CommandHandler("demo", demo_cmd))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.VOICE, voice_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(CallbackQueryHandler(locality_cb, pattern=r"^loc:"))
    app.add_handler(CallbackQueryHandler(material_cb, pattern=r"^mat:"))
    app.add_handler(CallbackQueryHandler(keypad_cb, pattern=r"^kg:"))
    app.add_handler(CallbackQueryHandler(again_cb, pattern=r"^again$"))
    app.add_error_handler(error_handler)
    log.info("bot starting (polling)")
    app.run_polling()


if __name__ == "__main__":
    main()
