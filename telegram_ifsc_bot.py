import logging
import pandas as pd
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

# ---------------- Logging ----------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------------- Env Vars ----------------
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
RENDER_EXTERNAL_HOSTNAME = os.getenv("RENDER_EXTERNAL_HOSTNAME")

if not TELEGRAM_TOKEN or not RENDER_EXTERNAL_HOSTNAME:
    raise ValueError("❌ Missing TELEGRAM_TOKEN or RENDER_EXTERNAL_HOSTNAME in env")

# Conversation states
STATE, BANK, BRANCH = range(3)

# ---------------- CSV Loader ----------------
CSV_FILE = "ifsc.csv"
df_cache = None
bank_dict = {}

def load_csv():
    global df_cache, bank_dict
    if df_cache is None:
        # सिर्फ जरूरी columns load करना
        usecols = ["State", "Bank", "Branch", "District", "Address", "IFSC", "MICR", "Contact"]
        df_cache = pd.read_csv(CSV_FILE, usecols=usecols, encoding_errors="ignore")

        # strip spaces
        for col in ["State", "Bank", "Branch"]:
            df_cache[col] = df_cache[col].astype(str).str.strip()

        # dictionary बनाओ (State -> Banks list)
        bank_dict = (
            df_cache.groupby("State")["Bank"]
            .unique()
            .apply(lambda x: [b.lower() for b in x])
            .to_dict()
        )

        logger.info(f"✅ CSV loaded with {len(df_cache)} rows")
    return df_cache

# ---------------- Search ----------------
def search_ifsc(state, bank, branch):
    df = load_csv()
    state, bank, branch = state.lower(), bank.lower(), branch.lower()

    # bank validation dictionary से
    if state not in [s.lower() for s in df["State"].unique()]:
        return None, f"❌ State '{state}' नहीं मिला।"

    if bank not in bank_dict.get(state.title(), []):
        return None, f"❌ Bank '{bank}' नहीं मिला।"

    # branch search pandas से
    matches = df[
        (df["State"].str.lower() == state) &
        (df["Bank"].str.lower() == bank) &
        (df["Branch"].str.lower().str.contains(branch))
    ]

    if matches.empty:
        # fuzzy branch match
        branches = df[
            (df["State"].str.lower() == state) &
            (df["Bank"].str.lower() == bank)
        ]["Branch"].str.lower().tolist()

        suggestions = difflib.get_close_matches(branch, branches, n=3, cutoff=0.5)
        if suggestions:
            return None, f"❌ Branch नहीं मिला। शायद आपका मतलब था: {', '.join(suggestions)}"
        else:
            return None, "❌ कोई branch नहीं मिली।"

    return matches, None

# ---------------- Handlers ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🌐 Visit Website", url="https://pmetromart.in/ifsc/")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "👋 Welcome to *IFSC Finder | PMetroMart!*\n\nकृपया अपना *State* लिखें:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )
    return STATE

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
        results, error = search_ifsc(state, bank, branch)

        if error:
            keyboard = [[InlineKeyboardButton("🌐 Visit Website", url="https://pmetromart.in/ifsc/")]]
            await update.message.reply_text(error, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            for _, row in results.iterrows():
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

    try:
        await asyncio.wait_for(process(), timeout=40)
    except asyncio.TimeoutError:
        keyboard = [[InlineKeyboardButton("🌐 Visit Website", url="https://pmetromart.in/ifsc/")]]
        await update.message.reply_text(
            "⌛ Search delay हो गया। कृपया website पर चेक करें।",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operation cancel कर दिया गया।")
    return ConversationHandler.END

# ---------------- Main ----------------
def main():
    df = load_csv()  # load once
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
