import logging
import pandas as pd
import chardet
import difflib
import os
import asyncio
from dotenv import load_dotenv
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

# ------------------ CSV Load ------------------
CSV_FILE = "ifsc.csv"
ifsc_dict = {}

def detect_encoding(file_path):
    with open(file_path, "rb") as f:
        result = chardet.detect(f.read())
    logger.info(f"✅ CSV Encoding: {result['encoding']}")
    return result["encoding"]

def load_csv():
    global ifsc_dict
    encoding = detect_encoding(CSV_FILE)
    df = pd.read_csv(CSV_FILE, encoding=encoding)

    # Normalize data
    df["State"] = df["State"].astype(str).str.strip().str.lower()
    df["Bank"] = df["Bank"].astype(str).str.strip().str.lower()
    df["Branch"] = df["Branch"].astype(str).str.strip().str.lower()

    # Build dictionary for fast lookup
    for _, row in df.iterrows():
        state = row["State"]
        bank = row["Bank"]
        branch = row["Branch"]

        if state not in ifsc_dict:
            ifsc_dict[state] = {}
        if bank not in ifsc_dict[state]:
            ifsc_dict[state][bank] = {}
        ifsc_dict[state][bank][branch] = row.to_dict()

    logger.info(f"✅ Dictionary built with {len(df)} records")

# ------------------ Helpers ------------------
def website_button():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🌐 Visit Website", url="https://pmetromart.in/ifsc/")
    ]])

# ------------------ Bot Handlers ------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to *IFSC Finder | PMetroMart*!\n\n"
        "कृपया अपना *State* लिखें:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=website_button()
    )
    return STATE

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ IFSC Finder Help\n\n"
        "1️⃣ /start - Bot शुरू करें\n"
        "2️⃣ State → Bank → Branch\n"
        "➡️ फिर Bot आपको IFSC देगा।",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=website_button()
    )

async def greet_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await start(update, context)

# --- State ---
async def get_state(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = update.message.text.strip().lower()

    if state not in ifsc_dict:
        await update.message.reply_text(
            "❌ State नहीं मिला। आप हमारी website पर भी check कर सकते हैं:",
            reply_markup=website_button()
        )
        return ConversationHandler.END

    context.user_data["state"] = state
    await update.message.reply_text("✅ State मिला! अब *Bank* का नाम भेजें:", parse_mode=ParseMode.MARKDOWN)
    return BANK

# --- Bank ---
async def get_bank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bank = update.message.text.strip().lower()
    state = context.user_data.get("state")

    if not state or state not in ifsc_dict:
        await update.message.reply_text(
            "❌ State error! आप हमारी website पर भी check कर सकते हैं:",
            reply_markup=website_button()
        )
        return ConversationHandler.END

    banks = list(ifsc_dict[state].keys())

    # ✅ Exact
    if bank in banks:
        context.user_data["bank"] = bank
        await update.message.reply_text("✅ Bank मिला! अब Branch का नाम भेजें:")
        return BRANCH

    # ✅ Fuzzy
    close_match = difflib.get_close_matches(bank, banks, n=1, cutoff=0.5)
    if close_match:
        matched_bank = close_match[0]
        context.user_data["bank"] = matched_bank
        await update.message.reply_text(
            f"🤖 आपने '{bank}' लिखा, मैंने समझा: *{matched_bank.title()}*\n\nअब Branch का नाम भेजें:",
            parse_mode=ParseMode.MARKDOWN
        )
        return BRANCH

    await update.message.reply_text(
        "❌ Bank नहीं मिला। आप हमारी website पर भी check कर सकते हैं:",
        reply_markup=website_button()
    )
    return ConversationHandler.END

# --- Branch ---
async def get_branch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    branch = update.message.text.strip().lower()
    state, bank = context.user_data.get("state"), context.user_data.get("bank")

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    async def process():
        branches = ifsc_dict.get(state, {}).get(bank, {})

        if not branches:
            await update.message.reply_text(
                "❌ Branch नहीं मिला। आप हमारी website पर भी check कर सकते हैं:",
                reply_markup=website_button()
            )
            return

        # ✅ Exact
        if branch in branches:
            row = branches[branch]
            msg = (
                f"🏦 *Bank:* {row['Bank'].title()}\n"
                f"🌍 *State:* {row['State'].title()}\n"
                f"🏙 *District:* {row['District']}\n"
                f"🏢 *Branch:* {row['Branch'].title()}\n"
                f"📌 *Address:* {row['Address']}\n"
                f"🔑 *IFSC:* `{row['IFSC']}`\n"
                f"💳 *MICR:* {row['MICR']}\n"
                f"📞 *Contact:* {row['Contact']}"
            )
            await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            return

        # ✅ Fuzzy
        close_match = difflib.get_close_matches(branch, list(branches.keys()), n=1, cutoff=0.5)
        if close_match:
            matched_branch = close_match[0]
            row = branches[matched_branch]
            msg = (
                f"🤖 आपने '{branch}' लिखा, मैंने समझा: *{matched_branch.title()}*\n\n"
                f"🏦 *Bank:* {row['Bank'].title()}\n"
                f"🌍 *State:* {row['State'].title()}\n"
                f"🏙 *District:* {row['District']}\n"
                f"🏢 *Branch:* {row['Branch'].title()}\n"
                f"📌 *Address:* {row['Address']}\n"
                f"🔑 *IFSC:* `{row['IFSC']}`\n"
                f"💳 *MICR:* {row['MICR']}\n"
                f"📞 *Contact:* {row['Contact']}"
            )
            await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            return

        await update.message.reply_text(
            "❌ कोई result नहीं मिला। आप हमारी website पर भी check कर सकते हैं:",
            reply_markup=website_button()
        )

    try:
        await asyncio.wait_for(process(), timeout=60)
    except asyncio.TimeoutError:
        await update.message.reply_text(
            "⌛ Result delay हो गया।\n👉 आप हमारी website पर भी check कर सकते हैं:",
            reply_markup=website_button()
        )

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operation cancel कर दिया गया।")
    return ConversationHandler.END

# ------------------ Main ------------------
def main():
    load_csv()  # load dictionary

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_state)],
            BANK: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_bank)],
            BRANCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_branch)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        conversation_timeout=120,
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
