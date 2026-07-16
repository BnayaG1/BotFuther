# Post-deploy checklist (Railway)

Run after first deploy and after each major release.

## Logs (Railway dashboard)

- [ ] `Bot is running. Starting Flask and Polling...`
- [ ] No `InvalidToken` / `409 Conflict`
- [ ] `Admin bot thread started` (if admin vars set)

## Public URL

- [ ] Open service URL — shows `Bot is running!`

## User bot

- [ ] `/start` — welcome + menu
- [ ] Send exercise image — draft + notebook
- [ ] `/quota` — trial or coupon quota

## Admin bot (if configured)

- [ ] `/start` — price keyboard
- [ ] Tap `₪150` → generate 1 code — message is code only

## Purchase flow

- [ ] Buy package → Bit instructions + WhatsApp link
- [ ] `ADMIN_CHAT_ID` — admin receives notification (if set)

## Persistence

- [ ] Create coupon via admin bot
- [ ] Trigger redeploy on Railway
- [ ] Redeem same coupon still works (volume `/data` + `COUPON_DB_PATH`)

## Local machine

- [ ] Stop local `python -m bot` while Railway is live
