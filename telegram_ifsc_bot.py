import logging
import os
import pandas as pd
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ConversationHandler, ContextTypes
)
from rapidfuzz import fuzz, process

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
STATE, BANK, BRANCH = range(3)

# Load CSV (with correct encoding)
df = pd.read_csv("ifsc.csv", dtype=str, encoding="latin1").fillna("N/A")

# Prepare unique lists
all_states = df["State"].str.upper().unique().tolist()
all_banks = df["Bank"].str.upper().unique().tolist()

# Bank aliases dictionary
BANK_ALIASES = {
    "sbi": "STATE BANK OF INDIA",
    "pnb": "PUNJAB NATIONAL BANK",
    "bob": "BANK OF BARODA",
    "hdfc": "HDFC BANK",
    "icici": "ICICI BANK",
    "axis": "AXIS BANK",
    "canara": "CANARA BANK",
    "union": "UNION BANK OF INDIA",
}

# Website button
def website_button():
    keyboard = [[InlineKeyboardButton("🌐 Visit Website", url="https://pmetromart.in/ifsc/")]]
    return InlineKeyboardMarkup(keyboard)

# Normalize bank name
def normalize_bank_name(user_input, all_banks):
    user_input = user_input.strip().upper()

    # alias check
    if user_input.lower() in BANK_ALIASES:
        return BANK_ALIASES[user_input.lower()]

    # fuzzy match
    match, score = process.extractOne(user_input, all_banks, scorer=fuzz.partial_ratio)
    if score >= 60:
        return match
    return None

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [[InlineKeyboardButton("🌐 Visit Website", url="https://pmetromart.in/ifsc/")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "👋 Welcome to IFSC Finder | PMetroMart!\n\n"
        "कृपया अपना *State* लिखें:",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    return STATE

# State input
async def state_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_state = update.message.text.strip().upper()
    match, score = process.extractOne(user_state, all_states, scorer=fuzz.partial_ratio)
    if score < 60:
        await update.message.reply_text(
            "❌ State नहीं मिला। आप हमारी website पर भी check कर सकते हैं:",
            reply_markup=website_button()
        )
        return STATE

    context.user_data["state"] = match
    await update.message.reply_text(f"✅ State मिला! अब *Bank* का नाम भेजें:", parse_mode="Markdown")
    return BANK

# Bank input
async def bank_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_bank = update.message.text.strip()
    bank_match = normalize_bank_name(user_bank, all_banks)

    if not bank_match:
        await update.message.reply_text(
            f"❌ Bank '{user_bank}' नहीं मिला।\nआप हमारी website पर भी check कर सकते हैं:",
            reply_markup=website_button()
        )
        return BANK

    context.user_data["bank"] = bank_match
    await update.message.reply_text(f"✅ Bank मिला! अब *Branch* का नाम भेजें:", parse_mode="Markdown")
    return BRANCH

# Branch input
async def branch_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_branch = update.message.text.strip().upper()
    state = context.user_data["state"]
    bank = context.user_data["bank"]

    subset = df[(df["State"].str.upper() == state) & (df["Bank"].str.upper() == bank)]
    if subset.empty:
        await update.message.reply_text(
            "❌ कोई branches नहीं मिली। आप website पर भी check कर सकते हैं:",
            reply_markup=website_button()
        )
        return ConversationHandler.END

    match, score = process.extractOne(user_branch, subset["Branch"].str.upper().tolist(), scorer=fuzz.partial_ratio)
    if score < 60:
        await update.message.reply_text(
            f"❌ Branch '{user_branch}' नहीं मिली।\nआप हमारी website पर भी check कर सकते हैं:",
            reply_markup=website_button()
        )
        return ConversationHandler.END

    branch_row = subset[subset["Branch"].str.upper() == match].iloc[0]

    msg = (
        f"🏦 *Bank:* {branch_row['Bank']}\n"
        f"🌍 *State:* {branch_row['State']}\n"
        f"🏙 *District:* {branch_row['District']}\n"
        f"🏢 *Branch:* {branch_row['Branch']}\n"
        f"📌 *Address:* {branch_row['Address']}\n"
        f"🔑 *IFSC:* `{branch_row['IFSC']}`\n"
        f"💳 *MICR:* {branch_row['MICR']}\n"
        f"📞 *Contact:* {branch_row['Contact']}"
    )

    await update.message.reply_text(msg, parse_mode="Markdown")
    return ConversationHandler.END

# Cancel
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Conversation रद्द कर दिया गया है।")
    return ConversationHandler.END

# Main
def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    app = ApplicationBuilder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, state_input)],
            BANK: [MessageHandler(filters.TEXT & ~filters.COMMAND, bank_input)],
            BRANCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, branch_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        conversation_timeout=60,
    )

    app.add_handler(conv_handler)
    app.run_polling()

if __name__ == "__main__":
    main()
