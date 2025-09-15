import os
import logging
import pandas as pd
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes,
)

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
STATE, BANK, BRANCH = range(3)

# Load IFSC data into dictionary (optimized with full row)
def load_ifsc_dict():
    try:
        df = pd.read_csv("ifsc.csv", encoding="ISO-8859-1")  # ✅ Fix encoding
    except UnicodeDecodeError:
        df = pd.read_csv("ifsc.csv", encoding="latin1")      # fallback

    ifsc_dict = {}
    for _, row in df.iterrows():
        state = str(row["State"]).strip().lower()
        bank = str(row["Bank"]).strip().lower()
        branch = str(row["Branch"]).strip().lower()

        branch_data = {
            "Bank": row["Bank"],
            "State": row["State"],
            "District": row["District"],
            "Branch": row["Branch"],
            "Address": row["Address"],
            "IFSC": row["IFSC"],
            "MICR": row["MICR"],
            "Contact": row["Contact"],
        }

        ifsc_dict.setdefault(state, {}).setdefault(bank, {})[branch] = branch_data
    return ifsc_dict

ifsc_dict = load_ifsc_dict()

# Website button
def website_button():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 Visit Website", url="https://pmetromart.in/ifsc/")]
    ])

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = website_button()
    await update.message.reply_text(
        "👋 Welcome to IFSC Finder | PMetroMart!\n\nकृपया अपना State लिखें:",
        reply_markup=keyboard
    )
    return STATE

# State input
async def state_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = update.message.text.strip().lower()
    if state in ifsc_dict:
        context.user_data["state"] = state
        await update.message.reply_text("✅ State मिला! अब Bank का नाम भेजें:")
        return BANK
    else:
        await update.message.reply_text(
            "❌ State नहीं मिला। आप हमारी website पर भी check कर सकते हैं:",
            reply_markup=website_button()
        )
        return ConversationHandler.END

# Bank input
async def bank_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bank = update.message.text.strip().lower()
    state = context.user_data.get("state")

    if state and bank in ifsc_dict[state]:
        context.user_data["bank"] = bank
        await update.message.reply_text("✅ Bank मिला! अब Branch का नाम भेजें:")
        return BRANCH
    else:
        await update.message.reply_text(
            "❌ Bank नहीं मिला। आप हमारी website पर भी check कर सकते हैं:",
            reply_markup=website_button()
        )
        return ConversationHandler.END

# Branch input
async def branch_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    branch = update.message.text.strip().lower()
    state = context.user_data.get("state")
    bank = context.user_data.get("bank")

    await update.message.reply_text(
        "🪔 Searching... अगर ज्यादा समय लगे तो आप हमारी website पर भी चेक कर सकते हैं:",
        reply_markup=website_button()
    )

    if state and bank and branch in ifsc_dict[state][bank]:
        row = ifsc_dict[state][bank][branch]
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
    else:
        await update.message.reply_text(
            "❌ Branch नहीं मिला। आप हमारी website पर भी check कर सकते हैं:",
            reply_markup=website_button()
        )
    return ConversationHandler.END

# Cancel
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operation cancel कर दिया गया।")
    return ConversationHandler.END

# Main
def main():
    TOKEN = os.getenv("TELEGRAM_TOKEN")
    HOSTNAME = os.getenv("RENDER_EXTERNAL_HOSTNAME")

    if not TOKEN or not HOSTNAME:
        raise ValueError("⚠️ TELEGRAM_TOKEN और RENDER_EXTERNAL_HOSTNAME env variables set करें।")

    app = Application.builder().token(TOKEN).build()

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

    # Webhook setup
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 10000)),
        url_path=TOKEN,
        webhook_url=f"https://{HOSTNAME}/{TOKEN}",
    )

if __name__ == "__main__":
    main()
