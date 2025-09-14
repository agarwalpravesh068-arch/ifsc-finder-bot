import logging
import pandas as pd
import chardet
import difflib
import os
import asyncio
from dotenv import load_dotenv
from datetime import datetime
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)
from flask import Flask

# 🔑 Load environment variables
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
RENDER_EXTERNAL_HOSTNAME = os.getenv("RENDER_EXTERNAL_HOSTNAME")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN not found (check .env or Render Environment Variables)")
if not RENDER_EXTERNAL_HOSTNAME:
    raise ValueError("❌ RENDER_EXTERNAL_HOSTNAME not found in environment variables")

print("✅ Loaded TELEGRAM_TOKEN:", TELEGRAM_TOKEN[:8] + "..." if TELEGRAM_TOKEN else "None")

# Conversation states
STATE, BANK, BRANCH = range(3)

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================== CSV Loading ==================
CSV_FILE = "ifsc.csv"
cached_df = None

def detect_encoding(file_path):
    with open(file_path, "rb") as f:
        result = chardet.detect(f.read())
    logger.info(f"✅ Detected Encoding: {result['encoding']}")
    return result["encoding"]

def load_csv():
    global cached_df
    if cached_df is None:
        encoding = detect_encoding(CSV_FILE)
        cached_df = pd.read_csv(CSV_FILE, encoding=encoding)
        logger.info(f"✅ CSV Loaded, total rows = {len(cached_df)}")

        cached_df["State"] = cached_df["State"].astype(str).str.strip()
        cached_df["Bank"] = cached_df["Bank"].astype(str).str.strip()
        cached_df["Branch"] = cached_df["Branch"].astype(str).str.strip()
    return cached_df

# ================== Search ==================
def search_ifsc(state, bank, branch):
    df = load_csv()
    state_lower = state.strip().lower()
    bank_lower = bank.strip().lower()
    branch_lower = branch.strip().lower()

    # ✅ Exact Match
    exact_result = df[
        (df["State"].str.lower() == state_lower) &
        (df["Bank"].str.lower() == bank_lower) &
        (df["Branch"].str.lower() == branch_lower)
    ]
    if not exact_result.empty:
        return exact_result, None

    # ✅ Fuzzy Suggestions (Branch only)
    branches = df[
        (df["State"].str.lower() == state_lower) &
        (df["Bank"].str.lower() == bank_lower)
    ]["Branch"].str.lower().tolist()
    suggestions = difflib.get_close_matches(branch_lower, branches, n=3, cutoff=0.4)

    # ✅ Partial Match fallback
    filtered_df = df[
        (df["State"].str.lower() == state_lower) &
        (df["Bank"].str.lower() == bank_lower) &
        (df["Branch"].str.lower().str.contains(branch_lower, na=False))
    ]
    return filtered_df, suggestions

# ================== Log Queries ==================
def log_query(user, state, bank, branch, result_count):
    log_data = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user_id": user.id,
        "username": user.username,
        "name": f"{user.first_name or ''} {user.last_name or ''}".strip(),
        "state": state,
        "bank": bank,
        "branch": branch,
        "results": result_count
    }
    df_log = pd.DataFrame([log_data])
    log_file = "queries_log.csv"
    df_log.to_csv(log_file, mode="a", header=not os.path.exists(log_file), index=False)
    logger.info(f"📝 Query Logged: {log_data}")

# ================== Commands ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to *IFSC Finder | PMetroMart*!\n\n"
        "कृपया अपना *State* लिखें:\n\n"
        "🌐 Visit our website: [PMetroMart IFSC Portal](https://pmetromart.in/ifsc/)",
        parse_mode="Markdown"
    )
    return STATE

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ *IFSC Finder Bot Help*\n\n"
        "1️⃣ /start - Bot शुरू करें\n"
        "2️⃣ State भेजें (जैसे: Delhi)\n"
        "3️⃣ Bank भेजें (जैसे: SBI)\n"
        "4️⃣ Branch भेजें (जैसे: Connaught)\n"
        "➡️ फिर Bot आपको IFSC details देगा।\n\n"
        "🌐 Visit website: [PMetroMart IFSC](https://pmetromart.in/ifsc/)",
        parse_mode="Markdown"
    )

# ✅ Hi / Hello Handler
async def greet_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await start(update, context)

async def get_state(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_state = update.message.text.strip()
    context.user_data["state"] = user_state
    logger.info(f"DEBUG: User Input -> State={user_state}")
    await update.message.reply_text("✅ State मिल गया!\nअब कृपया *Bank* का नाम भेजें:", parse_mode="Markdown")
    return BANK

async def get_bank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_bank = update.message.text.strip()
    context.user_data["bank"] = user_bank
    logger.info(f"DEBUG: User Input -> Bank={user_bank}, State={context.user_data.get('state')}")
    await update.message.reply_text("✅ Bank मिल गया!\nअब कृपया Branch का नाम भेजें:")
    return BRANCH

async def get_branch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_branch = update.message.text.strip()
    state = context.user_data.get("state")
    bank = context.user_data.get("bank")
    logger.info(f"DEBUG: User Input -> Branch={user_branch}, Bank={bank}, State={state}")

    # पहले ही बता दो कि search हो रहा है
    await update.message.reply_text("🔍 Searching your IFSC details, कृपया wait करें...")

    async def process_query():
        df, suggestions = search_ifsc(state, bank, user_branch)
        log_query(update.message.from_user, state, bank, user_branch, len(df))

        if df.empty:
            if suggestions:
                await update.message.reply_text(
                    f"❌ Exact result नहीं मिला।\n👉 Suggestions: {', '.join(suggestions)}"
                )
            else:
                await update.message.reply_text("❌ कोई result नहीं मिला।\nकृपया सही State/Bank/Branch नाम डालें।")
        else:
            for _, row in df.iterrows():
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

            await update.message.reply_text(
                "✅ Search पूरा हुआ।\nफिर से शुरू करने के लिए /start दबाएँ।",
                parse_mode="Markdown"
            )

    try:
        await asyncio.wait_for(process_query(), timeout=25)
    except asyncio.TimeoutError:
        await update.message.reply_text(
            "⌛ Result लोड होने में दिक्कत आ रही है।\n👉 Aap hamari website par bhi check kar sakte hai:\n\n"
            "[IFSC Finder](https://pmetromart.in/ifsc/)",
            parse_mode="Markdown"
        )

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operation cancel कर दिया गया।")
    return ConversationHandler.END

# ================== Flask App for Render ==================
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ IFSC Finder Bot is running!", 200

# ================== Main ==================
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
        conversation_timeout=60
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("help", help_command))

    greet_handler = MessageHandler(
        filters.Regex(r'^(hi|hello|hii|hey|namaste)$') & ~filters.COMMAND,
        greet_user
    )
    application.add_handler(greet_handler)

    PORT = int(os.environ.get("PORT", 10000))
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TELEGRAM_TOKEN,
        webhook_url=f"https://{RENDER_EXTERNAL_HOSTNAME}/{TELEGRAM_TOKEN}"
    )

    logger.info(f"🚀 Bot started in webhook mode at https://{RENDER_EXTERNAL_HOSTNAME}/{TELEGRAM_TOKEN}")

if __name__ == "__main__":
    main()
