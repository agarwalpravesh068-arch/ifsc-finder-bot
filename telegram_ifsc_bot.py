import logging
import pandas as pd
import chardet
import difflib
import os
import asyncio
from dotenv import load_dotenv
from datetime import datetime
from flask import Flask, request
from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

# ------------------ Logging ------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ------------------ Env Vars ------------------
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
RENDER_EXTERNAL_HOSTNAME = os.getenv("RENDER_EXTERNAL_HOSTNAME")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN missing (check Render env)")
if not RENDER_EXTERNAL_HOSTNAME:
    raise ValueError("❌ RENDER_EXTERNAL_HOSTNAME missing (check Render env)")

logger.info(f"✅ TELEGRAM_TOKEN loaded: {TELEGRAM_TOKEN[:8]}...")
logger.info(f"✅ RENDER_EXTERNAL_HOSTNAME: {RENDER_EXTERNAL_HOSTNAME}")

# Conversation states
STATE, BANK, BRANCH = range(3)

# ------------------ CSV Cache ------------------
CSV_FILE = "ifsc.csv"
cached_df = None

def detect_encoding(file_path):
    with open(file_path, "rb") as f:
        result = chardet.detect(f.read())
    logger.info(f"✅ CSV Encoding: {result['encoding']}")
    return result["encoding"]

def load_csv():
    global cached_df
    if cached_df is None:
        encoding = detect_encoding(CSV_FILE)
        cached_df = pd.read_csv(CSV_FILE, encoding=encoding)
        logger.info(f"✅ CSV Loaded, rows = {len(cached_df)}")
        cached_df["State"] = cached_df["State"].astype(str).str.strip()
        cached_df["Bank"] = cached_df["Bank"].astype(str).str.strip()
        cached_df["Branch"] = cached_df["Branch"].astype(str).str.strip()
    return cached_df

# ------------------ Search ------------------
def search_ifsc(state, bank, branch):
    df = load_csv()
    state_lower, bank_lower, branch_lower = state.lower(), bank.lower(), branch.lower()

    exact = df[
        (df["State"].str.lower() == state_lower) &
        (df["Bank"].str.lower() == bank_lower) &
        (df["Branch"].str.lower() == branch_lower)
    ]
    if not exact.empty:
        return exact, None

    branches = df[
        (df["State"].str.lower() == state_lower) &
        (df["Bank"].str.lower() == bank_lower)
    ]["Branch"].str.lower().tolist()
    suggestions = difflib.get_close_matches(branch_lower, branches, n=3, cutoff=0.4)

    partial = df[
        (df["State"].str.lower() == state_lower) &
        (df["Bank"].str.lower() == bank_lower) &
        (df["Branch"].str.lower().str.contains(branch_lower, na=False))
    ]
    return partial, suggestions

# ------------------ Bot Handlers ------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to *IFSC Finder | PMetroMart*!\n\n"
        "कृपया अपना *State* लिखें:\n\n"
        "🌐 Visit: https://pmetromart.in/ifsc/",
        parse_mode=ParseMode.MARKDOWN
    )
    return STATE

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ IFSC Finder Help\n\n"
        "1️⃣ /start - Bot शुरू करें\n"
        "2️⃣ State → Bank → Branch\n"
        "➡️ फिर Bot आपको IFSC देगा।\n\n"
        "🌐 Website: https://pmetromart.in/ifsc/",
        parse_mode=ParseMode.MARKDOWN
    )

async def greet_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await start(update, context)

async def get_state(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["state"] = update.message.text.strip()
    await update.message.reply_text("✅ State मिला! अब *Bank* का नाम भेजें:", parse_mode=ParseMode.MARKDOWN)
    return BANK

async def get_bank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["bank"] = update.message.text.strip()
    await update.message.reply_text("✅ Bank मिला! अब Branch का नाम भेजें:")
    return BRANCH

async def get_branch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    branch = update.message.text.strip()
    state, bank = context.user_data.get("state"), context.user_data.get("bank")

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    async def process():
        df, suggestions = search_ifsc(state, bank, branch)

        if df.empty:
            if suggestions:
                await update.message.reply_text(f"❌ Exact result नहीं मिला।\n👉 Suggestions: {', '.join(suggestions)}")
            else:
                await update.message.reply_text("❌ कोई result नहीं मिला।")
        else:
            for _, row in df.iterrows():
                msg = (
                    f"🏦 Bank: {row['Bank']}\n"
                    f"🌍 State: {row['State']}\n"
                    f"🏙 District: {row['District']}\n"
                    f"🏢 Branch: {row['Branch']}\n"
                    f"📌 Address: {row['Address']}\n"
                    f"🔑 IFSC: {row['IFSC']}\n"
                    f"💳 MICR: {row['MICR']}\n"
                    f"📞 Contact: {row['Contact']}"
                )
                await update.message.reply_text(msg)
            await update.message.reply_text("✅ Search पूरा हुआ।\n/start से दोबारा शुरू करें।")

    try:
        await asyncio.wait_for(process(), timeout=25)
    except asyncio.TimeoutError:
        await update.message.reply_text(
            "⌛ Result delay हो गया।\n👉 Website: https://pmetromart.in/ifsc/"
        )

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operation cancel कर दिया गया।")
    return ConversationHandler.END


# ------------------ Main with Flask ------------------
app = Flask(__name__)
application = Application.builder().token(TELEGRAM_TOKEN).build()

conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_state)],
        BANK: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_bank)],
        BRANCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_branch)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    conversation_timeout=60,
)
application.add_handler(conv_handler)
application.add_handler(CommandHandler("help", help_command))
application.add_handler(MessageHandler(filters.Regex(r'^(hi|hello|hey|namaste)$') & ~filters.COMMAND, greet_user))

@app.route("/", methods=["GET"])
def health_check():
    return "✅ IFSC Finder Bot running!", 200

@app.route(f"/{TELEGRAM_TOKEN}", methods=["POST"])
async def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return "OK", 200

def main():
    PORT = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
