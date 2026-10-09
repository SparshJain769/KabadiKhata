"""User-facing copy for the Kabadi Khata bot.

Primary language: **Hinglish** (romanized Hindi) — team decision, because it is
easier for low-literacy phone users to read than Devanagari. English is kept
alongside for the README, the demo and an easy toggle.

Usage:
    from bot.strings_hi import t, MATERIAL_LABELS
    t("welcome")                      # Hinglish (default)
    t("hisaab_summary", today_kg=37)  # with formatting
    t("welcome", lang="en")           # English
"""

LANG_DEFAULT = "hi"  # "hi" = Hinglish, "en" = English

HI = {
    "welcome": "Namaste! \U0001F64F Main *Kabadi Khata* hoon.\nAapke har collection ka pakka receipt banata hoon — bas photo kheencho, kaagaz-kaam main sambhal loonga.",
    "ask_name": "Pehle apna naam batao.",
    "name_saved": "Theek hai {name} ji! ✅",
    "ask_locality": "Aap kis ilaake mein kaam karte ho? Neeche se chuno \U0001F447",
    "locality_saved": "{locality} set ho gaya. ✅",
    "send_photo": "Ab taraazu (scale) aur maal ki ek photo bhejo \U0001F4F7",
    "after_photo": "Badhiya! Ab maal ka type aur weight batao —\nbutton dabao, ya voice note bhejo \U0001F3A4",
    "choose_material": "Maal kaun sa hai?",
    "enter_weight": "Kitne kilo? Number dabao.",
    "weight_prompt": "Weight (kg): {kg}",
    "processing": "Ek second... check kar raha hoon ✅",
    "receipt_ready": "Receipt ready! ✅ Yeh raha aapka pakka hisaab.",
    "question_prefix": "\U0001F914 ",  # agent's follow-up question is appended after this
    "answer_hint": "Sahi jawaab button se chuno ya dobara batao.",
    "hisaab_button": "\U0001F4CA Mera Hisaab",
    "hisaab_summary": (
        "\U0001F4CA *Mera Hisaab* — {name}\n\n"
        "Aaj: {today_kg} kg • ₹{today_inr}\n"
        "Is mahine: {month_kg} kg • ₹{month_inr}\n"
        "Total receipts: {count}\n"
        "✅ Chain verified"
    ),
    "help": "Photo bhejo → maal ka type aur kg batao → receipt milega. /hisaab se apna total dekho.",
    "error_generic": "Arre, kuch gadbad ho gayi. Dobara try karo. \U0001F647",
    "synthetic_notice": "(Demo data — asli collection nahi)",
    "btn_voice": "\U0001F3A4 Voice note",
    "btn_tap": "⌨️ Button se batao",
    "btn_yes": "Haan",
    "btn_no": "Nahi",
    "btn_confirm": "Pakka ✅",
    "btn_cancel": "Cancel",
    "btn_retry": "Dobara batao",
    "need_start": "Pehle /start karke naam aur ilaaka set karo.",
    "voice_soon": "Voice support aa raha hai — abhi button se batao.",
    "bad_weight": "Weight theek nahi laga. Dobara daalo (0–500 kg).",
    "cancelled": "Theek hai, cancel kar diya.",
    "demo_on": "Demo mismatch: ON",
    "demo_off": "Demo mismatch: OFF",
}

EN = {
    "welcome": "Hello! \U0001F64F I'm *Kabadi Khata*.\nI make a verified receipt for every collection — just send a photo and I'll handle the paperwork.",
    "ask_name": "First, tell me your name.",
    "name_saved": "Okay {name}! ✅",
    "ask_locality": "Which area do you work in? Pick below \U0001F447",
    "locality_saved": "{locality} set. ✅",
    "send_photo": "Now send one photo of the scale and the material \U0001F4F7",
    "after_photo": "Great! Now tell me the material and weight —\ntap the buttons, or send a voice note \U0001F3A4",
    "choose_material": "What material is it?",
    "enter_weight": "How many kg? Tap the number.",
    "weight_prompt": "Weight (kg): {kg}",
    "processing": "One second... checking ✅",
    "receipt_ready": "Receipt ready! ✅ Here is your verified record.",
    "question_prefix": "\U0001F914 ",
    "answer_hint": "Pick the correct answer or tell me again.",
    "hisaab_button": "\U0001F4CA My Account",
    "hisaab_summary": (
        "\U0001F4CA *My Account* — {name}\n\n"
        "Today: {today_kg} kg • ₹{today_inr}\n"
        "This month: {month_kg} kg • ₹{month_inr}\n"
        "Total receipts: {count}\n"
        "✅ Chain verified"
    ),
    "help": "Send a photo → tell me the material and kg → get a receipt. Use /hisaab for your totals.",
    "error_generic": "Sorry, something went wrong. Please try again. \U0001F647",
    "synthetic_notice": "(Demo data — not a real collection)",
    "btn_voice": "\U0001F3A4 Voice note",
    "btn_tap": "⌨️ Use buttons",
    "btn_yes": "Yes",
    "btn_no": "No",
    "btn_confirm": "Confirm ✅",
    "btn_cancel": "Cancel",
    "btn_retry": "Tell me again",
    "need_start": "Please /start first to set your name and area.",
    "voice_soon": "Voice support is coming — please use the buttons for now.",
    "bad_weight": "That weight doesn't look right. Enter again (0-500 kg).",
    "cancelled": "Okay, cancelled.",
    "demo_on": "Demo mismatch: ON",
    "demo_off": "Demo mismatch: OFF",
}

# Material labels shown on the tap-button grid (Hinglish primary).
MATERIAL_LABELS = {
    "PET":           {"hi": "Plastic bottle", "en": "Plastic bottle (PET)"},
    "HDPE":          {"hi": "Hard plastic",   "en": "Hard plastic (HDPE)"},
    "LDPE_film":     {"hi": "Polythene/film", "en": "Polythene / film"},
    "mixed_plastic": {"hi": "Mixed plastic",  "en": "Mixed plastic"},
    "cardboard":     {"hi": "Gatta/carton",   "en": "Cardboard / carton"},
    "paper":         {"hi": "Raddi/kaagaz",   "en": "Paper / newspaper"},
    "metal":         {"hi": "Loha/metal",     "en": "Metal"},
    "ewaste":        {"hi": "E-waste",        "en": "E-waste"},
    "unknown":       {"hi": "Pata nahi",      "en": "Unknown"},
}

# Material order for the button grid.
MATERIAL_ORDER = ["PET", "HDPE", "LDPE_film", "mixed_plastic", "cardboard", "paper", "metal", "ewaste"]


def t(key: str, lang: str = LANG_DEFAULT, **kwargs) -> str:
    """Return a string by key in the chosen language, formatted with kwargs.

    Falls back to English, then to the key itself, so a missing key never crashes the bot.
    """
    table = HI if lang == "hi" else EN
    s = table.get(key)
    if s is None:
        s = EN.get(key, key)
    return s.format(**kwargs) if kwargs else s


def material_label(material: str, lang: str = LANG_DEFAULT) -> str:
    """Hinglish/English display label for a material code; falls back to the code."""
    entry = MATERIAL_LABELS.get(material)
    if entry is None:
        return material
    return entry.get(lang, entry.get("en", material))
