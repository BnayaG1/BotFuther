# Railway setup (after GitHub push)

## 1. Create service

1. Open [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo**
2. Select the private `BotFuther` repository
3. Railway detects `Dockerfile` and `railway.toml` automatically

## 2. Volume (required)

1. Service → **Volumes** → **Add Volume**
2. Mount path: `/data`
3. Set variable: `COUPON_DB_PATH=/data/coupons.db`

Without the volume, coupons and user access reset on every redeploy.

## 3. Environment variables

Copy from local `.env` into Railway **Variables** (never commit `.env`).

| Variable | Required | Notes |
|----------|----------|-------|
| `TELEGRAM_BOT_TOKEN` | Yes | User bot (@BotFather) |
| `GEMINI_VISION_API_KEY` | Yes | Vision API |
| `COUPON_DB_PATH` | Yes | `/data/coupons.db` |
| `ADMIN_BOT_TOKEN` | No | Admin coupon bot |
| `ADMIN_USER_IDS` | No | e.g. `843647241` |
| `BIT_PHONE` | No | Bit payment phone |
| `PAYMENT_CONFIRM_WHATSAPP_URL` | No | WhatsApp confirm link |
| `ADMIN_CHAT_ID` | No | Purchase notifications |
| `GEMINI_MODEL` | No | Default in code if unset |
| `VISION_QUALITY_MODEL` | No | Default in code if unset |

See [`.env.example`](../.env.example) for optional vision/cost flags.

## 4. Deploy settings (already in `railway.toml`)

- `numReplicas = 1` — **do not scale to 2** (Telegram polling conflict / 409)
- Health check: `GET /` → `Bot is running!`

## 5. First deploy logs

Expect:

```
Bot is running. Starting Flask and Polling...
Admin bot thread started
```

No `InvalidToken`, no `409 Conflict`.

## 6. Before going live

- Stop local `python -m bot` on your PC (only one poller allowed)
- Open the public Railway URL → should show `Bot is running!`
- Run [POST_DEPLOY_CHECKLIST.md](./POST_DEPLOY_CHECKLIST.md)
