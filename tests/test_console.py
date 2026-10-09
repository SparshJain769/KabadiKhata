"""Tests for the console: pure logic + a Streamlit AppTest smoke run (headless)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from console import logic  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
APP = str(ROOT / "console" / "app.py")


# ---- pure logic ----
def test_load_flags():
    flags = logic.load_flags()
    assert len(flags) == 3
    rules = {f["rule"] for f in flags}
    assert rules == {"R1_mass_balance", "R2_duplicate_photos", "R3_chain_integrity"}


def test_load_certificates():
    threshold, certs = logic.load_certificates()
    assert threshold == 80
    assert len(certs) == 3


def test_inflow_vs_claim_r1_only():
    r1 = next(f for f in logic.load_flags() if f["rule"] == "R1_mass_balance")
    bar = logic.inflow_vs_claim(r1)
    assert bar["claimed"] == 190.0 and bar["verified"] == 5.0 and bar["ratio"] == 38.0
    r3 = next(f for f in logic.load_flags() if f["rule"] == "R3_chain_integrity")
    assert logic.inflow_vs_claim(r3) is None


def test_backed_badge():
    assert logic.backed_badge(94, 80) == "ok"
    assert logic.backed_badge(80, 80) == "ok"
    assert logic.backed_badge(3, 80) == "low"


def test_apply_decision():
    f = logic.load_flags()[0]
    out = logic.apply_decision(f, "inspect", "auditor_1", "2026-10-09T10:00:00+00:00")
    assert out["status"] == "inspection_requested" and out["decided_by"] == "auditor_1"
    assert logic.apply_decision(f, "dismiss", "auditor_1", "t")["status"] == "dismissed"
    assert f["status"] == "open"  # original not mutated


def test_rule_label():
    assert "Mass balance" in logic.rule_label("R1_mass_balance")
    assert logic.rule_label("unknown_rule") == "unknown_rule"


# ---- Streamlit AppTest smoke (headless, no browser) ----
def test_app_runs_both_roles_without_exception():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    assert not at.exception
    # switch to Brand
    at.sidebar.radio[0].set_value("Brand").run()
    assert not at.exception


def test_app_run_radar_shows_flags():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    at.button[0].click().run()  # "Run radar"
    assert not at.exception
    assert at.session_state["radar_ran"] is True
