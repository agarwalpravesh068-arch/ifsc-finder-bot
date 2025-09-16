import os
from dotenv import load_dotenv
import mysql.connector
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
from datetime import datetime
import asyncio

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# States
STATE, BANK, BRANCH = range(3)

# Load CSV
df = pd.read_csv("ifsc.csv", dtype=str, encoding="latin1", on_bad_lines="skip").fillna("N/A")

# Unique values
states = sorted(df["State"].str.strip().unique())
banks = sorted(df["Bank"].str.strip().unique())

# Aliases
BANK_ALIASES = {
    "SBI": "STATE BANK OF INDIA",
    "PNB": "PUNJAB NATIONAL BANK",
    "HDFC": "HDFC BANK",
    "ICICI": "ICICI BANK",
    "BOB": "BANK OF BARODA",
    "BOI": "BANK OF INDIA",
    "CANARA": "CANARA BANK",
}

# Website button
def website_button():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🌐 Visit Website", url="https://pmetromart.in/ifsc/")]]
    )

import mysql.connector  # <-- Add this import at the top

# ---------------- Logging Queries ----------------
def log_query(user, state, bank, branch, result_count):
    log_file = "queries_log.csv"
    log_data = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user_id": user.id,
        "username": user.username,
        "name": f"{user.first_name or ''} {user.last_name or ''}".strip(),
        "state": state,
        "bank": bank,
        "branch": branch,
        "results": result_count,
    }

    # ✅ Save to CSV
    df_log = pd.DataFrame([log_data])
    df_log.to_csv(log_file, mode="a", header=not os.path.exists(log_file), index=False)
    logger.info(f"📝 Query Logged (CSV): {log_data}")

    # ✅ Save to MySQL
    try:

        conn = mysql.connector.connect(
            host=os.getenv("MYSQL_HOST"),
            user=os.getenv("MYSQL_USER"),
            password=os.getenv("MYSQL_PASSWORD"),
            database=os.getenv("MYSQL_DB")
port=3306
        )
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO queries_log (time, user_id, username, name, state, bank, branch, results)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            log_data["time"],
            log_data["user_id"],
            log_data["username"],
            log_data["name"],
            log_data["state"],
            log_data["bank"],
            log_data["branch"],
            log_data["results"],
        ))
        conn.commit()
        cursor.close()
        conn.close()
        logger.info("✅ Query Logged in MySQL")
    except Exception as e:
        logger.error(f"❌ MySQL Logging Failed: {e}")

# ---------------- Handlers ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    name = user.first_name if user and user.first_name else "User"

    welcome_msg = (
        f"👋 Welcome *{name}* to IFSC Finder | PMetroMart!\n\n"
        "🔍 *How to use this bot:*\n"
        "1️⃣ Enter your *State* name (e.g., Delhi)\n"
        "2️⃣ Enter your *Bank* name (e.g., SBI or HDFC)\n"
        "3️⃣ Enter your *Branch* name (e.g., Connaught Place)\n\n"
        "✅ Bot will instantly show you IFSC, MICR, Address, Contact details.\n\n"
        "🌐 You can also visit our website: [PMetroMart IFSC Finder](https://pmetromart.in/ifsc/)\n\n"
        "➡️ Start by typing your *State* now 👇"
    )

    await update.message.reply_text(welcome_msg, parse_mode="Markdown", reply_markup=website_button())
    return STATE
async def state_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_state = update.message.text.strip().upper()
    match = process.extractOne(user_state, states, scorer=fuzz.WRatio)
    if match and match[1] > 80:
        context.user_data["state"] = match[0]
        await update.message.reply_text(f"✅ State मिला! अब *BANK* का नाम भेजें:", parse_mode="Markdown")
        return BANK
    await update.message.reply_text("❌ State नहीं मिला।", reply_markup=website_button())
    return ConversationHandler.END

async def bank_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_bank = update.message.text.strip().upper()

    if user_bank in BANK_ALIASES:
        bank_name = BANK_ALIASES[user_bank]
    else:
        match = process.extractOne(user_bank, banks, scorer=fuzz.WRatio)
        bank_name = match[0] if match and match[1] > 80 else None

    if bank_name:
        context.user_data["bank"] = bank_name
        await update.message.reply_text(f"✅ Bank मिला! अब *BRANCH* का नाम भेजें:", parse_mode="Markdown")
        return BRANCH

    await update.message.reply_text(f"❌ Bank '{user_bank}' नहीं मिला।", reply_markup=website_button())
    return ConversationHandler.END

async def branch_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_branch = update.message.text.strip().upper()
    state = context.user_data.get("state")
    bank = context.user_data.get("bank")

    if not state or not bank:
        await update.message.reply_text("⚠️ Session expired. कृपया /start करें।")
        return ConversationHandler.END

    await update.message.reply_text("⌛ Searching... कृपया wait करें:", reply_markup=website_button())

    # Filter dataframe
    subset = df[
        (df["State"].str.upper() == state.upper()) &
        (df["Bank"].str.upper() == bank.upper())
    ]

    if subset.empty:
        await update.message.reply_text("❌ No branches found.", reply_markup=website_button())
        log_query(update.message.from_user, state, bank, user_branch, 0)
        return ConversationHandler.END

    # Fuzzy branch
    branches = subset["Branch"].str.strip().unique()
    match = process.extractOne(user_branch, branches, scorer=fuzz.WRatio)

    if not match or match[1] < 70:
        await update.message.reply_text(f"❌ Branch '{user_branch}' नहीं मिला।", reply_markup=website_button())
        log_query(update.message.from_user, state, bank, user_branch, 0)
        return ConversationHandler.END

    branch_name = match[0]
    result = subset[subset["Branch"].str.strip().str.upper() == branch_name.upper()]

    # Send results
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

    # ✅ Log query
    log_query(update.message.from_user, state, bank, user_branch, len(result))

    # ✅ 10s later send thank you msg
    async def delayed_thank_you():
        await asyncio.sleep(10)
        await update.message.reply_text(
            "🙏 Thank you for choosing *IFSC Finder | PMetroMart*!\n\n"
            "🔄 दुबारा IFSC code search करने के लिए /start दबाएँ\n"
            "🌐 या हमारी website पर visit करें:",
            parse_mode="Markdown",
            reply_markup=website_button()
        )
    asyncio.create_task(delayed_thank_you())

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Conversation cancelled.")
    return ConversationHandler.END

# ---------------- Main ----------------
def main():
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise ValueError("❌ TELEGRAM_TOKEN not found in env!")

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
