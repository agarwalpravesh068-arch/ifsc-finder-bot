import logging
import pandas as pd
import chardet
import difflib
import os
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

# ------------------ CSV Preload & Dictionary Index ------------------
CSV_FILE = "ifsc.csv"
lookup = {}  # {state: {bank: {branch: row_dict}}}

def detect_encoding(file_path):
    with open(file_path, "rb") as f:
        result = chardet.detect(f.read())
    return result["encoding"]

def load_csv():
    global lookup
    if lookup:
        return lookup

    encoding = detect_encoding(CSV_FILE)
    df = pd.read_csv(CSV_FILE, encoding=encoding)
    df = df.fillna("")

    for _, row in df.iterrows():
        state = str(row["State"]).strip().lower()
        bank = str(row["Bank"]).strip().lower()
        branch = str(row["Branch"]).strip().lower()

        if state not in lookup:
            lookup[state] = {}
        if bank not in lookup[state]:
            lookup[state][bank] = {}
        lookup[state][bank][branch] = row.to_dict()

    logger.info(f"✅ Dictionary Index Ready: {len(df)} rows indexed")
    return lookup

# ------------------ Search Function ------------------
def search_ifsc(state, bank, branch):
    load_csv()
    state, bank, branch = state.strip().lower(), bank.strip().lower(), branch.strip().lower()

    # ✅ Exact match
    if state in lookup and bank in lookup[state] and branch in lookup[state][bank]:
        return [lookup[state][bank][branch]], None

    # ✅ Fuzzy suggestions
    suggestions = []
    if state in lookup and bank in lookup[state]:
        all_branches = list(lookup[state][bank].keys())
        suggestions = difflib.get_close_matches(branch, all_branches, n=3, cutoff=0.4)

    return [], suggestions

# ------------------ Bot Handlers ------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to *IFSC Finder | PMetroMart*!\n\n"
        "कृपया अपना *State* लिखें:",
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

    results, suggestions = search_ifsc(state, bank, branch)

    if results:
        for row in results:
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

    elif suggestions:
        await update.message.reply_text(f"❌ Exact result नहीं मिला।\n👉 Suggestions: {', '.join(suggestions)}")

    else:
        keyboard = [[InlineKeyboardButton("🌐 Open IFSC Finder Website", url="https://pmetromart.in/ifsc/")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "❌ कोई result नहीं मिला।\n👉 आप हमारी वेबसाइट पर भी check कर सकते हैं:",
            reply_markup=reply_markup
        )

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🌐 Open IFSC Finder Website", url="https://pmetromart.in/ifsc/")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "❌ Operation cancel कर दिया गया।\n👉 आप हमारी वेबसाइट पर भी check कर सकते हैं:",
        reply_markup=reply_markup
    )
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
