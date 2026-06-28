# Beam Solver — Telegram Bot

בוט טלגרם לחילוץ תרגילי סטטיקה מתמונה, טיוטת אישור, חישוב ריאקציות ופתרון מחברת.

## התקנה

```powershell
cd BotFuther
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# ערוך .env — הוסף TELEGRAM_BOT_TOKEN ו-GEMINI_API_KEY
```

## הרצה

```powershell
python -m bot
```

## מבנה

| תיקייה | תפקיד |
|--------|--------|
| `bot/` | לוגיקת הבוט, vision, טיוטה, handlers |
| `core/` | ויזואליזציה ומנוע סטטיקה |
| `solver.py` | חישובי קורה (מחברת) |
| `beam_notebook.py` | רינדור PDF/PNG של פתרון מחברת |
| `validator_images/` | regression ל-vision |
| `tests/` | בדיקות |

## בדיקות

```powershell
python -m pytest tests/ -q
python -m bot.vision_regression
```

## GitHub

אל תעלה `.env` — רק `.env.example`.

```powershell
git init
git add .
git commit -m "Initial bot package"
git remote add origin https://github.com/YOUR_USER/beam-solver-bot.git
git push -u origin main
```
