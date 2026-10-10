# WhatsApp channel — demo runbook (Twilio Sandbox)

The bot runs on **WhatsApp in production; Telegram for the prototype** (CLAUDE.md #7).
This runbook shows the WhatsApp channel running on the **Twilio WhatsApp Sandbox** —
real WhatsApp, no business verification — for the demo video. The Telegram bot is
unchanged and still works.

The adapter (`bot/whatsapp_webhook.py`) reuses the same core as the Telegram bot
(`api_client` → the real API, `cards`, `strings_hi`). WhatsApp has no kg keypad, so
the flow is: **send a photo → reply with a numbered material menu → type the number →
type the kg**. On a pass you get the receipt card; on a mismatch, the agent's one
Hindi question and no receipt. Voice notes are out of scope here (same as the bot).

## One-time setup (these steps need your accounts — only you can do them)

1. **Twilio account** → Console → *Messaging → Try it out → Send a WhatsApp message*.
   Activate the **WhatsApp Sandbox**: from your phone's WhatsApp, send `join <code>`
   to the sandbox number Twilio shows. Your number is now linked to the sandbox.
2. **Copy credentials** from the Twilio Console into `.env` (gitignored):
   ```
   TWILIO_ACCOUNT_SID=AC...
   TWILIO_AUTH_TOKEN=...
   ```
3. **ngrok**: install, add your authtoken (`ngrok config add-authtoken <token>`).

## Each demo run

1. **Seed + API** (the ledger the bot writes to):
   ```
   make seed
   make api            # FastAPI on :3000
   ```
2. **WhatsApp webhook**:
   ```
   make whatsapp       # uvicorn bot.whatsapp_webhook:app on :8080
   ```
3. **Tunnel** the webhook and copy the https URL:
   ```
   ngrok http 8080
   ```
   Put that URL in `.env` so Twilio can fetch the receipt card back:
   ```
   WHATSAPP_PUBLIC_URL=https://<your-subdomain>.ngrok-free.app
   ```
   Restart `make whatsapp` after setting it (it is read at startup).
4. **Point the sandbox at the webhook**: Twilio Console → WhatsApp Sandbox Settings →
   *When a message comes in* → `https://<your-subdomain>.ngrok-free.app/whatsapp`,
   method **POST**. Save.
5. From your phone, message the sandbox: **send a photo of the scale + material**,
   then reply with the **material number**, then the **kg**. You get the receipt card.
   To show the refusal, enter a weight that disagrees with the photo. Send `hisaab`
   for the income card.

## Notes / honest caveats

- The sandbox shows a **"Twilio Sandbox"** header and needs the `join <code>` opt-in —
  both visible on camera. Mention in the video that this is the sandbox; the
  production channel is the WhatsApp Business/Cloud API.
- The webhook and card URL are the only new moving parts. If the card image round-trip
  misbehaves on camera, the fallback is already discussed in the PR: reply with the
  receipt details as text (ID, kg, ₹, hash) and keep the card image for Telegram.
- `MOCK_LLM=1` (default) makes the backend read every photo as 12 kg PET, so tap 12 kg
  for a pass and anything else for a refusal, exactly like the Telegram demo. With a
  real vision key (`KK_USE_MOCK=0` is already set by `make whatsapp`; set `MOCK_LLM=0`
  and a `GEMINI_API_KEY`) the real photo reading applies.
