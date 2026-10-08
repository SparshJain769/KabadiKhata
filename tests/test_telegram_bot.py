import asyncio
import io
import os
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from PIL import Image

import bot.telegram_bot as tb
from bot import strings_hi
from bot.cards import make_receipt_card

ROOT = Path(__file__).resolve().parent.parent


def _cbs(markup):
    return [b.callback_data for row in markup.inline_keyboard for b in row]


def test_keypad_append_dot_back():
    assert tb.apply_keypad("", "5") == "5"
    assert tb.apply_keypad("", ".") == "0."
    assert tb.apply_keypad("12", ".") == "12."
    assert tb.apply_keypad("12", "back") == "1"
    assert tb.apply_keypad("", "back") == ""
    assert tb.apply_keypad("1", "zzz") == "1"


def test_keypad_double_dot_and_cap():
    assert tb.apply_keypad("1.5", ".") == "1.5"
    assert tb.apply_keypad("123456", "7") == "123456"
    assert tb.apply_keypad("12345", ".") == "12345."
    assert tb.apply_keypad("123456", ".") == "123456"


def test_parse_kg():
    assert tb.parse_kg("12.5") == 12.5
    assert tb.parse_kg("500") == 500.0
    for bad in ["0", "0.0", "501", "", "abc", "nan", "1e3", "1_0", "1.", "-3", "inf"]:
        assert tb.parse_kg(bad) is None, bad


def test_build_payload():
    p = tb.build_payload(42, "seelampur", "PET", 3, True, "abc")
    assert p == {"collector_id": "kab_42", "locality": "seelampur",
                 "taps": {"material": "PET", "kg": 3.0}, "photo_b64": "abc", "simulate": "mismatch"}
    q = tb.build_payload(42, "seelampur", "PET", 3, False)
    assert q["simulate"] is None and q["photo_b64"] is None


def test_resize_for_upload_rgb_jpeg_big():
    buf = io.BytesIO()
    Image.new("RGBA", (3000, 1500), (255, 0, 0, 128)).save(buf, format="PNG")
    out = tb.resize_for_upload(buf.getvalue())
    img = Image.open(io.BytesIO(out))
    assert img.format == "JPEG" and img.mode == "RGB"
    assert max(img.size) <= 1024


def test_keyboards():
    loc = _cbs(tb.locality_keyboard())
    assert len(loc) == len(tb.LOCALITIES) and all(c.startswith("loc:") for c in loc)
    mat = _cbs(tb.material_keyboard())
    assert len(mat) == len(strings_hi.MATERIAL_ORDER) and all(c.startswith("mat:") for c in mat)
    kg = _cbs(tb.kg_keyboard())
    assert len(kg) == 13 and all(c.startswith("kg:") for c in kg)
    assert "kg:back" in kg and "kg:ok" in kg and "kg:." in kg


def test_contract_payload_to_card():
    p = tb.build_payload(1, "seelampur", "PET", 5.5, False)
    resp = tb.api.collect(p)
    assert resp["status"] == "receipt"
    assert make_receipt_card(resp["receipt"]).startswith(b"\x89PNG\r\n\x1a\n")


def test_all_used_string_keys_exist():
    src = (ROOT / "bot" / "telegram_bot.py").read_text(encoding="utf-8")
    keys = set(re.findall(r'\bt\(\s*"([a-z_]+)"', src)) | {"demo_on", "demo_off"}
    assert keys
    for k in keys:
        assert k in strings_hi.HI and k in strings_hi.EN, k


def test_env_loader_bom_and_comment(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_bytes("﻿# comment\n\nKK_TEST_TOKEN=abc123\nKK_KEEP=new\n".encode("utf-8"))
    monkeypatch.delenv("KK_TEST_TOKEN", raising=False)
    monkeypatch.setenv("KK_KEEP", "old")
    tb.load_env(f)
    assert os.environ["KK_TEST_TOKEN"] == "abc123"
    assert os.environ["KK_KEEP"] == "old"
    monkeypatch.delenv("KK_TEST_TOKEN", raising=False)


def test_import_without_token():
    env = {k: v for k, v in os.environ.items() if k != "TELEGRAM_BOT_TOKEN"}
    r = subprocess.run([sys.executable, "-c", "import bot.telegram_bot"], cwd=ROOT, env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def _cb_update(data):
    update = MagicMock()
    update.callback_query.data = data
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    msg = MagicMock()
    msg.reply_text = AsyncMock()
    msg.reply_photo = AsyncMock()
    update.effective_message = msg
    update.effective_user.id = 7
    return update, msg


def _ctx(ud):
    c = MagicMock()
    c.user_data = ud
    return c


def test_material_tap_shows_keypad():
    ud = {"name": "Raju", "locality": "seelampur", "state": "choosing_material",
          "pending": {"material": None, "kg_buf": "", "photo_b64": None}}
    update, msg = _cb_update("mat:PET")
    asyncio.run(tb.material_cb(update, _ctx(ud)))
    update.callback_query.answer.assert_awaited_once()
    assert ud["pending"]["material"] == "PET" and ud["state"] == "entering_kg"
    assert _cbs(msg.reply_text.await_args.kwargs["reply_markup"]) == _cbs(tb.kg_keyboard())


def test_kg_ok_collects_and_sends_receipt():
    ud = {"name": "Raju", "locality": "seelampur", "state": "entering_kg",
          "pending": {"material": "PET", "kg_buf": "12.5", "photo_b64": None}}
    update, msg = _cb_update("kg:ok")
    asyncio.run(tb.keypad_cb(update, _ctx(ud)))
    msg.reply_photo.assert_awaited_once()
    assert msg.reply_photo.await_args.kwargs["photo"].startswith(b"\x89PNG")
    assert ud["state"] == "ready"


def test_kg_ok_mismatch_demo_fires_once():
    ud = {"name": "Raju", "locality": "seelampur", "state": "entering_kg", "simulate_mismatch": True,
          "pending": {"material": "PET", "kg_buf": "20", "photo_b64": None}}
    update, msg = _cb_update("kg:ok")
    asyncio.run(tb.keypad_cb(update, _ctx(ud)))
    msg.reply_photo.assert_not_awaited()
    assert ud["state"] == "awaiting_answer" and ud["simulate_mismatch"] is False


def test_kg_ok_invalid_stays():
    ud = {"name": "Raju", "locality": "seelampur", "state": "entering_kg",
          "pending": {"material": "PET", "kg_buf": "", "photo_b64": None}}
    update, msg = _cb_update("kg:ok")
    asyncio.run(tb.keypad_cb(update, _ctx(ud)))
    assert ud["state"] == "entering_kg"
    assert msg.reply_text.await_args.args[0] == strings_hi.t("bad_weight")


def test_hisaab_sends_income_image():
    ud = {"name": "Raju", "locality": "seelampur", "state": "ready"}
    update, msg = _cb_update("")  # provides effective_message + effective_user.id
    asyncio.run(tb.hisaab_cmd(update, _ctx(ud)))
    msg.reply_photo.assert_awaited_once()
    assert msg.reply_photo.await_args.kwargs["photo"][:8] == b"\x89PNG\r\n\x1a\n"


def test_hisaab_before_registration():
    update, msg = _cb_update("")
    asyncio.run(tb.hisaab_cmd(update, _ctx({})))
    msg.reply_photo.assert_not_awaited()
    assert msg.reply_text.await_args.args[0] == strings_hi.t("need_start")


def test_unregistered_callback_routes_to_start():
    ud = {}
    update, msg = _cb_update("mat:PET")
    asyncio.run(tb.material_cb(update, _ctx(ud)))
    assert ud["state"] == "need_name"
    assert msg.reply_text.await_args_list[0].args[0] == strings_hi.t("need_start")
