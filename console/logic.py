"""Pure helpers for the Kabadi Khata console (no Streamlit import, so it is testable).

Loads the mock flags/certificates and computes the small derived values the UI
shows. Swaps to the real API (/radar/run, /provenance) later; these functions
keep the same shapes.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_MOCK = REPO_ROOT / "data" / "mock"

RULE_LABELS = {
    "R1_mass_balance": "R1 · Mass balance",
    "R2_duplicate_photos": "R2 · Duplicate photos",
    "R3_chain_integrity": "R3 · Chain integrity",
}


def rule_label(rule: str) -> str:
    return RULE_LABELS.get(rule, rule)


def load_flags() -> list[dict]:
    return json.loads((_MOCK / "flags.json").read_text(encoding="utf-8"))["flags"]


def load_certificates() -> tuple[int, list[dict]]:
    data = json.loads((_MOCK / "certificates.json").read_text(encoding="utf-8"))
    return int(data.get("threshold_pct", 80)), data["certificates"]


def inflow_vs_claim(flag: dict) -> dict | None:
    """For an R1 flag, the claimed vs verified-inflow tonnes (for the bar)."""
    if flag.get("rule") != "R1_mass_balance":
        return None
    d = flag.get("detail", {})
    return {
        "claimed": float(d.get("tonnes_claimed", 0)),
        "verified": float(d.get("verified_inflow_tonnes", 0)),
        "ratio": float(d.get("ratio", 0)),
    }


def backed_badge(pct: float, threshold: int) -> str:
    """'ok' if a certificate meets the verified-backed threshold, else 'low'."""
    return "ok" if pct >= threshold else "low"


def apply_decision(flag: dict, decision: str, by: str, ts: str) -> dict:
    """Return a copy of the flag with an auditor decision recorded.

    decision: 'inspect' -> status 'inspection_requested'; 'dismiss' -> 'dismissed'.
    """
    status = {"inspect": "inspection_requested", "dismiss": "dismissed"}.get(decision, flag.get("status"))
    out = dict(flag)
    out["status"] = status
    out["decided_by"] = by
    out["decided_ts"] = ts
    return out
