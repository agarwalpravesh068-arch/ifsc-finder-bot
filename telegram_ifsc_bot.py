import os
import logging
import pandas as pd
from rapidfuzz import process, fuzz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# States
STATE, BANK, BRANCH = range(3)

# Load data safely with memory optimization
df = pd.read_csv("ifsc.csv", dtype=str, encoding="latin1", on_bad_lines="skip").fillna("N/A")

# Create dictionaries for fast lookup
states = sorted(df["State"].str.strip().unique())
banks = sorted(df["Bank"].str.strip().unique())

state_dict = {s.lower(): s for s in states}
bank_dict = {b.lower(): b for b in banks}

# Bank aliases
BANK_ALIASES = {
    "sbi": "STATE BANK OF INDIA",
    "pnb": "PUNJAB NATIONAL BANK",
    "hdfc": "HDFC BANK",
    "icici": "ICICI BANK",
    "bob": "BANK OF BARODA",
    "boi": "BANK OF INDIA",
    "canara": "CANARA BANK",
}

# Website button
def website_button():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🌐 Visit Website", url="https://pmetromart.in/ifsc/")]]
    )

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to IFSC Finder | PMetroMart!\nकृपया अपना *State* लिखें:",
        parse_mode="Markdown",
        reply_markup=website_button()
    )
    return STATE

# State handler
async def state_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_state = update.message.text.strip().lower()
    match = process.extractOne(user_state, states, scorer=fuzz.WRatio)
    if match and match[1] > 80:
        context.user_data["state"] = match[0]
        await update.message.reply_text(f"✅ State मिला! अब *Bank* का नाम भेजें:", parse_mode="Markdown")
        return BANK
    await update.message.reply_text("❌ State नहीं मिला।", reply_markup=website_button())
    return ConversationHandler.END

# Bank handler
async def bank_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_bank = update.message.text.strip().lower()

    # Check aliases
    if user_bank in BANK_ALIASES:
        bank_name = BANK_ALIASES[user_bank]
    else:
        match = process.extractOne(user_bank, banks, scorer=fuzz.WRatio)
        bank_name = match[0] if match and match[1] > 80 else None

    if bank_name:
        context.user_data["bank"] = bank_name
        await update.message.reply_text(f"✅ Bank मिला! अब *Branch* का नाम भेजें:", parse_mode="Markdown")
        return BRANCH

    await update.message.reply_text(f"❌ Bank '{user_bank}' नहीं मिला।", reply_markup=website_button())
    return ConversationHandler.END

# Branch handler
async def branch_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_branch = update.message.text.strip().lower()
    state = context.user_data.get("state")
    bank = context.user_data.get("bank")

    if not state or not bank:
        await update.message.reply_text("⚠️ Session expired. कृपया /start करें।")
        return ConversationHandler.END

    await update.message.reply_text("⌛ Searching... अगर ज्यादा समय लगे तो आप हमारी website पर भी check कर सकते हैं:", reply_markup=website_button())

    # Filter dataframe
    subset = df[(df["State"].str.lower() == state.lower()) & (df["Bank"].str.lower() == bank.lower())]

    if subset.empty:
        await update.message.reply_text("❌ No branches found.", reply_markup=website_button())
        return ConversationHandler.END

    # Fuzzy branch match
    branches = subset["Branch"].str.strip().unique()
    match = process.extractOne(user_branch, branches, scorer=fuzz.WRatio)
    if not match or match[1] < 70:
        await update.message.reply_text(f"❌ Branch '{user_branch}' नहीं मिला।", reply_markup=website_button())
        return ConversationHandler.END

    branch_name = match[0]
    result = subset[subset["Branch"].str.strip().str.lower() == branch_name.lower()]

    for _, row in result.iterrows():
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
        await update.message.reply_text(msg, parse_mode="Markdown")

    return ConversationHandler.END

# Cancel handler
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Conversation cancelled.")
    return ConversationHandler.END

def main():
    token = os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("Telegram Bot Token not found in environment variables!")

    application = Application.builder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, state_handler)],
            BANK: [MessageHandler(filters.TEXT & ~filters.COMMAND, bank_handler)],
            BRANCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, branch_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)

    port = int(os.environ.get("PORT", 8080))
    app_url = os.getenv("RENDER_EXTERNAL_HOSTNAME")

    if app_url:
        application.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=token,
            webhook_url=f"https://{app_url}/{token}",
        )
    else:
        application.run_polling()

if __name__ == "__main__":
    main()
