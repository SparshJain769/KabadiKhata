# Kabadi Khata: implementation rules

This repo is our entry for **Environmental Hacks** (WeMakeDevs × AWS Bharat Builds Tour), **Waste and Energy track**.
- **Plan:** [`research/KABADI_KHATA_SCOPED_DOWN.md`](research/KABADI_KHATA_SCOPED_DOWN.md). Follow it for scope, owners and timeline.
- **2-day priorities:** [`research/TWO_DAY_SCOPE.md`](research/TWO_DAY_SCOPE.md). Read it first — it sets what to build in what order when time is short.
- **Vocabulary:** [`CONTEXT.md`](CONTEXT.md). Use its terms in code, UI and the video (e.g. **Certificate**, never "Claim").
- **This file:** the rules every change must follow, plus the fixes from our plan review. Where the plan and this file disagree, **this file wins**.

## What we're building (one paragraph)
A kabadiwala sends a photo of the scale plus a Hindi voice note (or taps buttons) to a Telegram bot. A Strands agent reads the photo and the voice note and checks they agree. If they do, it writes **one** hash-chained receipt and sends back a receipt card. If not, it asks one question in Hindi and writes nothing. An auditor console runs a deterministic fraud radar over seeded recycler data and approves inspections. Cedar decides who sees what. Everything runs locally (**Build It only**).

## Priority when time is short (2 build days: Fri Oct 9 + Sat Oct 10; ship Sun Oct 11)
Build the **spine (P0)** first and do not start anything else until all 4 beats run end-to-end on the real stack. Full detail and cut lines in [`research/TWO_DAY_SCOPE.md`](research/TWO_DAY_SCOPE.md).
1. **Receipt with a refusal** — photo + voice/taps → agent → on mismatch ask ONE Hindi question and write nothing; on pass write one hash-chained receipt + card.
2. **Fraud caught** — radar flags Recycler C (R1 mass balance) → auditor requests inspection.
3. **Tamper breaks the chain** — edit a receipt → `/verify` shows the broken seq.
4. **Cedar denial** — brand is denied a kabadiwala's identity; provenance only in aggregate.

**Infra (decided Fri morning, see [`docs/adr/0001-fastapi-sqlite-demo-stack.md`](docs/adr/0001-fastapi-sqlite-demo-stack.md)):** the demo runs on **FastAPI + SQLite**, not SAM + OpenSearch. `template.yaml` plus a `sam local invoke` clip covers the SAM visual; Strands + Cedar satisfy the AWS requirement. Fix #1 (SAM ↔ OpenSearch networking) no longer applies. **OpenSearch is back as a read-only search copy** ([ADR 0002](docs/adr/0002-opensearch-as-read-only-search-copy.md)): SQLite stays the ledger, and nothing in the spine may depend on OpenSearch.

## Hard constraints
- **Build It only.** No AWS account, Bedrock, S3, DynamoDB or Cognito. The AWS open-source tools we use: **Strands Agents, Cedar, SAM CLI (`sam local invoke`), OpenSearch** (read-only search copy, ADR 0002).
- **LLM:** Gemini (or OpenAI) through Strands' non-Bedrock model provider. Always pass the model explicitly, because Strands defaults to Bedrock.
- **Perception (P1) is the exception:** `read_photo` and `transcribe` call their providers directly, not through Strands. Photos: Groq (`qwen/qwen3.8-27b`, rotating `GROQ_API_KEYS`) first via `VISION_PROVIDER=groq`, then Gemini, OpenAI or xAI as fallbacks. Voice: Sarvam Saaras, then Gemini. None of these is an AWS service, so Build It still holds; the code checks every answer either way.
- **Hackathon rules:** no code written before the clock started; repo history must match the event dates; every member commits every day; list the AI coding tools used in the README; credit every dataset, icon and library with its licence.
- **Never commit secrets.** API keys and the Telegram token live in `.env` (gitignored). `.env.example` has placeholders only.
- **Only build what appears in the 3-minute video.** Anything else waits until after submission.

## Design rules (do not break)
1. **Code decides, the human approves, the LLM explains.** Fraud verdicts come from deterministic rules in `src/radar/rules.py`. The LLM only writes the explanation. The auditor approves the action.
2. **The agent has exactly one write tool,** `create_receipt`. It refuses unless `check_consistency` returned `ok` **and** Cedar allows `Agent::"kabadi-agent"` to `create_receipt`. Present Cedar as *the policy layer that holds even if the agent code changes*, not as a second, independent check.
3. **Label every synthetic thing as synthetic,** in the data (`synthetic: true`), the UI (a watermark or badge) and the video.
4. **Determinism for the demo:** temperature 0, a disk cache keyed by input sha256, and a `MOCK_LLM=1` replay mode for tests and rate-limit emergencies.

## Required fixes (from the plan review). Every one must be in the code.

### Fixes that will otherwise break the build
1. ~~**SAM ↔ OpenSearch networking.**~~ *Obsolete since ADR 0001 (no OpenSearch). Kept for history.* Lambda containers cannot reach `localhost:9200`.
   - Run `sam local start-api --docker-network <compose network name> --warm-containers EAGER`.
   - Read the OpenSearch host from env (`OPENSEARCH_HOST`): `opensearch:9200` inside SAM, `localhost:9200` for scripts and tests on the host.
   - Fallback: `host.docker.internal:9200`.
   - Pin the network name in `docker-compose.yml` (`networks: kk-net: name: kk-net`) so it's predictable.
2. **Lambda timeout and memory.** The default 3-second timeout kills every vision and audio call. In `template.yaml`:
   ```yaml
   Globals:
     Function:
       Timeout: 60
       MemorySize: 1024
       Runtime: python3.12
   ```
   Third-party packages go in a Lambda layer that `make lambda-deps` cross-installs for Linux arm64 **on the host** with uv (pinned from `uv.lock`); do not go back to `sam build --use-container`, which took 30+ minutes because Docker's network on the demo Mac is ~40x slower. New runtime dependencies only need `pyproject.toml` + `uv.lock`. The demo machine is an Apple Silicon Mac, so also set `Architectures: [arm64]` (x86 containers run under slow emulation). Keep a single collection request under ~25 s end to end, so it would also survive a real API Gateway's 29 s limit.
3. **Telegram voice notes are OGG/Opus.**
   - Convert to WAV (16 kHz mono) or MP3 **in the bot process on the laptop** (`pydub` plus a system ffmpeg) before calling `POST /collections`. The Lambda container has no ffmpeg.
   - Resize photos to ≤1024 px on the long side before base64-encoding.

### Fixes that raise the score
4. **"Verified-backed %" on every certificate.** This turns the "radar only sees supply inside the system" limitation into a feature.
   - `GET /provenance/{certificate_id}` returns `verified_backed_pct = verified receipt tonnes linked to the recycler / tonnes claimed × 100`.
   - The Brand console shows it as a column, with a badge at a configurable threshold (default **80%**).
   - Pitch line: *brands only buy certificates that are at least 80% verified-backed.*
5. **Radar sensitivity sweep, not a circular 100%.** In the seeded world:
   - Plant recycler fraud at **1.2×, 1.5×, 3× and 38×**, each as its own synthetic recycler or scenario.
   - Add realistic noise to the honest recyclers (±10–15% month to month).
   - `eval/radar_eval.py` reports the **smallest ratio caught with zero false flags on honest recyclers**, plus precision/recall per rule.
   - Put that number in the README and the video.
6. **Held-out photo evaluation.** The photos are the team's 30 AI-generated kabadi scale images (Kaggle `oneshikaaa/kabadiwala`, labelled synthetic), split 20 for tuning and 10 held out in `data/eval_photos/labels.csv` (`split` column); the held-out labels are confirmed by a person. Real phone photos go in the same file as `set=real` and are reported separately. Prompts are tuned on the tuning set only. `eval/photo_eval.py` reports kg accuracy (within ±5%, plus within ±1 kg) and material accuracy **on the held-out set only**, and states n.
7. **Give Raju a real reason to use it: a verified income statement.**
   - The "मेरा हिसाब" (my account) button returns a shareable **image**: name, month, receipt count, total kg, total ₹, chain-verified ✓, and a QR code linking to the verify endpoint.
   - Frame it as proof of income (e.g. for PM SVANidhi-style micro-loans).
   - The rate-card price stays, labelled **"indicative"**. It is not the pitch.
   - Say "WhatsApp in production; Telegram for the prototype" in the README and the video.
8. **Pitch line must match the source.** Use exactly:
   > *"In 2024, the NGT took up CPCB's finding of 6 lakh fake recycling (EPR) certificates from four plastic recyclers."*
   - Source: https://www.scconline.com/blog/post/2024/07/31/ngt-issues-notice-cpcb-moefcc-recovery-of-6-lakh-fake-epr-certificates-from-plastic-recycling-companies/ (NGT notice; news item dated July 2024).
   - Do **not** claim an audit year, that brands "held" the certificates, a tonnage, or a fine amount unless another cited source states it.
   - Do **not** call it a 2026 scandal.
   - "38×" is **our simulated case**, never a CPCB finding.
9. **Video trim.** Fold the "मेरा हिसाब" shot into the phone-flow segment. Show the architecture as a ~10-second overlay, not a separate slide. Give the time saved to the tamper demo and the Recycler C flag.

### Smaller implementation notes
- **Cedar entity references:** `Receipt.collector` and `Certificate.buyer` must be **entity references** (`Actor::"<id>"`), not plain `collector_id` strings. Otherwise `resource.collector == principal` never matches. Build the entities from the SQLite store (`ledger.store.Store`) in `authz.py`; the OpenSearch copy is never an authority.
- Cedar policies are default deny. Every API handler calls `is_allowed(principal, action, resource, context)` **before** touching data, and returns HTTP 403 with `{"denied_by": "cedar", "action": ...}`. The console renders this as the red "Denied by Cedar policy" banner.
- Hash chain: canonical JSON (sorted keys, fixed float format, UTC ISO timestamps). `prev_hash = "GENESIS"` for seq 0. `verify(collector_id)` returns the first broken seq.
- Perceptual hash duplicate check: compare Hamming distance in Python against stored hashes (fine at ~1,000 receipts). The threshold is tuned on edited copies of our own photos.
- Builder Center blog: do it after a safe submission (18:00–20:00 on Day 3). It's a separate prize, so it's worth an hour if time allows.

## Commands
- `make up` / `make down` start and stop OpenSearch (optional; Docker)
- `make seed` creates the SQLite database, loads the synthetic world and copies it to OpenSearch if it's up
- `make reindex` rebuilds the OpenSearch copy from SQLite
- `make api` runs the FastAPI app
- `make sam-invoke` builds the arm64 Lambda (deps layer built on the host) and runs two `sam local invoke`s for the video: a receipt written and a Cedar denial (~40 s)
- `make bot` and `make console`
- `make test`
- `make demo` runs everything above in order (OpenSearch is skipped if Docker isn't running). **It must work from a fresh clone in ≤ 10 minutes.**

## Definition of done for any feature
It runs end to end on the real stack (not just in a unit test), it has at least one test, synthetic data is labelled, nothing secret is committed, and it appears in the demo script. Otherwise it waits.
