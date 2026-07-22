# Beam Solver — Telegram Bot

בוט טלגרם לחילוץ תרגילי סטטיקה מתמונה, טיוטת אישור, חישוב ריאקציות ופתרון מחברת.

## התקנה מקומית

```powershell
cd BotFuther
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
copy .env.example .env
# ערוך .env — הוסף TELEGRAM_BOT_TOKEN ו-GEMINI_VISION_API_KEY
```

## הרצה מקומית

```powershell
python -m bot
```

הפעל **רק מופע אחד** (מקומי או Railway — לא שניהם).

## מבנה

| תיקייה | תפקיד |
|--------|--------|
| `bot/` | טלגרם, vision, טיוטה, handlers, גישה/רכישה |
| `core/` | מנוע סטטיקה, validation, מרכז כובד |
| `notebook/` | רינדור PDF/PNG של פתרון מחברת |
| `personal_assistant/` | מדריך פתרון שלב-אחר-שלב |
| `assets/` | תמונות בנק תרגילים ונוסחאות |
| `validator_images/` | regression ל-vision |
| `tests/` | בדיקות |
| `docs/` | הוראות Deploy (Railway) |

## בדיקות

```powershell
pip install -r requirements-dev.txt
python -m pytest tests/ -q
python -m bot.vision_regression
```

## Deploy ל-Railway (GitHub)

### 1. GitHub

אל תעלה `.env` או `coupons.db` — רק `.env.example`.

```powershell
# אחרי יצירת repo פרטי ב-GitHub:
powershell -ExecutionPolicy Bypass -File .\scripts\publish-github.ps1 -ForceMain
```

או לחיצה כפולה על `scripts\push-now.cmd` (עוקף את חסימת הסקריפטים).

או ידנית:

```powershell
git remote add origin https://github.com/YOUR_USER/botfuther.git
git push -u origin master
```

מומלץ: repo **פרטי**.

פרטים מלאים: [`docs/RAILWAY_SETUP.md`](docs/RAILWAY_SETUP.md)

### 2. Railway

1. [railway.app](https://railway.app) → New Project → Deploy from GitHub repo
2. **Volume** — mount לנתיב `/data`
3. **Variables** (בדשבורד, לא בקוד):

| משתנה | חובה | הערה |
|--------|------|------|
| `TELEGRAM_BOT_TOKEN` | כן | בוט משתמשים |
| `GEMINI_VISION_API_KEY` | כן | Vision API |
| `ADMIN_BOT_TOKEN` | לא | בוט אדמין |
| `ADMIN_USER_IDS` | לא | מספר user ID |
| `COUPON_DB_PATH` | כן | `/data/coupons.db` |
| `BIT_PHONE` | לא | תשלום בביט |
| `PAYMENT_CONFIRM_WHATSAPP_URL` | לא | וואטסאפ |
| `ADMIN_CHAT_ID` | לא | התראות רכישה |

העתק את שאר ה-flags מ-`.env.example` לפי הצורך.

4. Deploy — ב-Logs אמור להופיע:
   - `Bot is running. Starting Flask and Polling...`
   - `Admin bot thread started` (אם הוגדר אדמין)
5. URL ציבורי → `Bot is running!`

`railway.toml` מגדיר `numReplicas = 1` (חובה לטלגרם polling).

### 3. אחרי העלאה

| בדיקה | ציפייה |
|--------|--------|
| `/start` | הודעת פתיחה |
| תמונה | טיוטה + מחברת |
| `/quota` | מכסה |
| בוט אדמין `₪150` | קוד בלבד |
| Redeploy | קופונים נשמרים ב-volume |

### 4. תחזוקה

- גבה את `/data/coupons.db` פעם בשבוע
- אל תריץ `python -m bot` מקומית כשהשרת פעיל
- קודי קופון — דרך בוט האדמין בלבד

## Docker (מקומי)

```powershell
docker build -t beam-bot .
docker run --env-file .env -p 8080:8080 beam-bot
```
