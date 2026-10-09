"""Kabadi Khata console (Streamlit) — Auditor and Brand views, built against mock data.

Run:  streamlit run console/app.py      (use the venv)

Two roles (sidebar):
- Auditor: run the fraud radar, see flags with evidence, Request inspection / Dismiss.
- Brand:   see its certificates with a verified-backed % + badge, provenance in
           aggregate, and a red "Denied by Cedar policy" banner on identity access.

All data here is SYNTHETIC. Swaps to P3's real API (/radar/run, /provenance) later.
"""
from __future__ import annotations

import datetime

import pandas as pd
import streamlit as st

try:  # `streamlit run console/app.py` puts console/ on the path; tests import as a package
    from console.logic import (
        apply_decision, backed_badge, inflow_vs_claim,
        load_certificates, load_flags, rule_label,
    )
except ImportError:  # pragma: no cover
    from logic import (
        apply_decision, backed_badge, inflow_vs_claim,
        load_certificates, load_flags, rule_label,
    )

st.set_page_config(page_title="Kabadi Khata console", page_icon="♻️", layout="wide")


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def auditor_view() -> None:
    st.header("Auditor — fraud radar")
    st.caption("Code decides the flag · the LLM only explains · the auditor approves. Data is synthetic.")

    if st.button("▶ Run radar", type="primary"):
        st.session_state["radar_ran"] = True
    if not st.session_state.get("radar_ran"):
        st.info("Click **Run radar** to scan the seeded recycler data.")
        return

    flags = load_flags()
    decisions = st.session_state.setdefault("decisions", {})

    # summary table
    rows = []
    for f in flags:
        d = decisions.get(f["flag_id"])
        rows.append({
            "Flag": f["flag_id"],
            "Rule": rule_label(f["rule"]),
            "Subject": f.get("subject_name", f["subject_id"]),
            "Score": f["score"],
            "Status": (d["status"] if d else f["status"]),
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    for f in flags:
        decided = decisions.get(f["flag_id"])
        status = decided["status"] if decided else f["status"]
        with st.expander(f"{f['flag_id']} — {rule_label(f['rule'])} — {f.get('subject_name','')}  ·  {status}"):
            st.write(f["explanation_en"])
            st.caption(f["explanation_hi"])

            bar = inflow_vs_claim(f)
            if bar is not None:
                st.subheader(f"Claimed vs verified inflow  ·  {bar['ratio']:.0f}× gap")
                st.bar_chart(
                    pd.DataFrame({"tonnes": [bar["claimed"], bar["verified"]]},
                                 index=["Claimed", "Verified inflow"]),
                    color="#1d7a48",
                )
            elif f["rule"] == "R2_duplicate_photos":
                det = f.get("detail", {})
                c1, c2 = st.columns(2)
                c1.metric("Receipts in cluster", det.get("cluster_size"))
                c2.metric("Distinct photos", det.get("distinct_photos"))
                st.caption("(Side-by-side duplicate photos render here once real phashes exist.)")
            elif f["rule"] == "R3_chain_integrity":
                st.metric("Chain broken at seq", f.get("detail", {}).get("broken_at_seq"))

            st.write(f"**Evidence:** {', '.join(f.get('evidence_ids', [])) or '—'}")
            c1, c2, _ = st.columns([1, 1, 3])
            if c1.button("Request inspection", key="insp_" + f["flag_id"]):
                decisions[f["flag_id"]] = apply_decision(f, "inspect", "auditor_1", _now_iso())
                st.rerun()
            if c2.button("Dismiss", key="dis_" + f["flag_id"]):
                decisions[f["flag_id"]] = apply_decision(f, "dismiss", "auditor_1", _now_iso())
                st.rerun()
            if decided:
                st.success(f"{decided['status']} by {decided['decided_by']} at {decided['decided_ts']}")


def brand_view() -> None:
    st.header("Brand — my EPR certificates")
    threshold, certs = load_certificates()
    st.caption(f"A certificate is trustworthy at ≥ {threshold}% verified-backed. Data is synthetic.")

    rows = []
    for c in certs:
        badge = "🟢 OK" if backed_badge(c["verified_backed_pct"], threshold) == "ok" else "🔴 LOW"
        rows.append({
            "Certificate": c["certificate_id"],
            "Recycler": c.get("recycler_name", c["recycler_id"]),
            "Material": c["material"],
            "Tonnes claimed": c["tonnes_claimed"],
            "Verified-backed %": c["verified_backed_pct"],
            "": badge,
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    labels = [f"{c['certificate_id']} ({c['recycler_name']})" for c in certs]
    pick = st.selectbox("Inspect a certificate's provenance", labels)
    cert = certs[labels.index(pick)]

    if backed_badge(cert["verified_backed_pct"], threshold) == "low":
        st.error(f"⚠ {cert['certificate_id']} is only {cert['verified_backed_pct']}% verified-backed "
                 f"(threshold {threshold}%). Do not buy.")
    else:
        st.success(f"{cert['certificate_id']} is {cert['verified_backed_pct']}% verified-backed.")

    st.subheader("Provenance (aggregate)")
    prov = cert.get("provenance_aggregate", [])
    st.dataframe(
        pd.DataFrame([{"Locality": p["locality"].replace("_", " ").title(),
                       "Receipts": p["receipts"], "Tonnes": p["tonnes"]} for p in prov]),
        hide_index=True, use_container_width=True,
    )

    if st.button("Show collector identities"):
        st.error("🔒 Denied by Cedar policy: a brand cannot read kabadiwala identities. "
                 "Provenance is shown in aggregate only.")


def main() -> None:
    st.sidebar.title("♻️ Kabadi Khata")
    role = st.sidebar.radio("Role", ["Auditor", "Brand"])
    st.sidebar.caption("Synthetic demo data — not real collections.")
    if role == "Auditor":
        auditor_view()
    else:
        brand_view()


main()
