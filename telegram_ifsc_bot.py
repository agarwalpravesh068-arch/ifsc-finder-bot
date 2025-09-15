import logging
import pandas as pd
import os
import asyncio
from dotenv import load_dotenv
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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

# ------------------ Load CSV into Dictionary ------------------
CSV_FILE = "ifsc.csv"
ifsc_dict = {}

def load_ifsc_dict():
    global ifsc_dict
    df = pd.read_csv(CSV_FILE, dtype=str).fillna("")
    for _, row in df.iterrows():
        key = (row["State"].strip().lower(),
               row["Bank"].strip().lower(),
               row["Branch"].strip().lower())
        ifsc_dict[key] = row.to_dict()
    logger.info(f"✅ IFSC Dictionary loaded with {len(ifsc_dict)} entries")

load_ifsc_dict()

# ------------------ Search ------------------
def search_ifsc(state, bank, branch):
    key = (state.strip().lower(), bank.strip().lower(), branch.strip().lower())
    return ifsc_dict.get(key, None)

# ------------------ Common Website Button ------------------
def get_website_button():
    keyboard = [[InlineKeyboardButton("🌐 Visit Website", url="https://pmetromart.in/ifsc/")]]
    return InlineKeyboardMarkup(keyboard)

# ------------------ Bot Handlers ------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to *IFSC Finder | PMetroMart*!\n\n"
        "कृपया अपना *State* लिखें:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_website_button()
    )
    return STATE

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ IFSC Finder Help\n\n"
        "1️⃣ /start - Bot शुरू करें\n"
        "2️⃣ State → Bank → Branch\n"
        "➡️ फिर Bot आपको IFSC देगा।",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_website_button()
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
        row = search_ifsc(state, bank, branch)
        if not row:
            await update.message.reply_text(
                "❌ Result नहीं मिला।\n👉 आप हमारी website पर चेक कर सकते हैं:",
                reply_markup=get_website_button()
            )
        else:
            msg = (
                f"🏦 *Bank:* {row['Bank']}\n"
                f"🌍 *State:* {row['State']}\n"
                f"🏙 *District:* {row['District']}\n"
                f"🏢 *Branch:* {row['Branch']}\n"
                f"📌 *Address:* {row['Address']}\n"
                f"🔑 *IFSC:* `{row['IFSC']}`\n"
                f"💳 *MICR:* {row['MICR']}\n"
                f"📞 *Contact:* {row['Contact']}"
            )
            await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

            await update.message.reply_text(
                "✅ Search पूरा हुआ।",
                reply_markup=get_website_button()
            )

    try:
        await asyncio.wait_for(process(), timeout=60)  # timeout = 60s
    except asyncio.TimeoutError:
        await update.message.reply_text(
            "⌛ Search delay हो गया।\n👉 आप हमारी website पर चेक कर सकते हैं:",
            reply_markup=get_website_button()
        )

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operation cancel कर दिया गया।", reply_markup=get_website_button())
    return ConversationHandler.END

# ------------------ Main ------------------
def main():
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

    PORT = int(os.environ.get("PORT", 10000))
    webhook_url = f"https://{RENDER_EXTERNAL_HOSTNAME}/{TELEGRAM_TOKEN}"

    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TELEGRAM_TOKEN,
        webhook_url=webhook_url,
    )

if __name__ == "__main__":
    main()
