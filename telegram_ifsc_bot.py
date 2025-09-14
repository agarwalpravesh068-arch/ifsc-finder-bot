import logging
import pandas as pd
import chardet
import difflib
import os
from dotenv import load_dotenv
from datetime import datetime
from telegram import Update, ChatAction
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters,
    CallbackContext, ConversationHandler
)

# 🔑 Load environment variables
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN not found (check .env file or Render Environment Variables)")
print("✅ Loaded TELEGRAM_TOKEN:", TELEGRAM_TOKEN[:8] + "..." if TELEGRAM_TOKEN else "None")


# Conversation states
STATE, BRANCH = range(2)

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================== CSV Loading (Cache + Pre-Indexing) ==================
CSV_FILE = "ifsc.csv"
cached_df = None
state_branch_index = {}

def detect_encoding(file_path):
    with open(file_path, "rb") as f:
        result = chardet.detect(f.read())
    logger.info(f"✅ Detected Encoding: {result['encoding']}")
    return result["encoding"]

def load_and_index_csv():
    global cached_df, state_branch_index
    if cached_df is None:
        encoding = detect_encoding(CSV_FILE)
        cached_df = pd.read_csv(CSV_FILE, encoding=encoding)
        logger.info(f"✅ CSV Loaded, total rows = {len(cached_df)}")

        # Pre-indexing (State → Branches)
        state_branch_index = {}
        for _, row in cached_df.iterrows():
            state = str(row["State"]).strip().lower()
            branch = str(row["Branch"]).strip().lower()
            if state not in state_branch_index:
                state_branch_index[state] = set()
            state_branch_index[state].add(branch)

    return cached_df

# ================== Search Function ==================
def search_ifsc(state, branch):
    df = load_and_index_csv()
    state_lower = state.lower().strip()
    branch_lower = branch.lower().strip()

    # ✅ Exact Match First
    exact_result = df[
        (df["State"].str.lower() == state_lower) &
        (df["Branch"].str.lower() == branch_lower)
    ]
    if not exact_result.empty:
        logger.info(f"✅ Exact match found: {len(exact_result)} rows")
        return exact_result, None

    # ✅ Fuzzy Match (Top 3 suggestions)
    suggestions = []
    if state_lower in state_branch_index:
        all_branches = list(state_branch_index[state_lower])
        matches = difflib.get_close_matches(branch_lower, all_branches, n=3, cutoff=0.4)
        logger.info(f"🔍 Fuzzy suggestions for '{branch}': {matches}")
        if matches:
            suggestions = matches

    filtered_df = df[
        (df["State"].str.lower() == state_lower) &
        (df["Branch"].str.contains(branch, case=False, na=False))
    ]
    return filtered_df, suggestions

# ================== Log Queries ==================
def log_query(user, state, branch, result_count):
    log_data = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user_id": user.id,
        "username": user.username,
        "name": f"{user.first_name or ''} {user.last_name or ''}".strip(),
        "state": state,
        "branch": branch,
        "results": result_count
    }
    df_log = pd.DataFrame([log_data])
    log_file = "queries_log.csv"
    df_log.to_csv(log_file, mode="a", header=not os.path.exists(log_file), index=False)
    logger.info(f"📝 Query Logged: {log_data}")

# ================== Commands ==================
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "👋 Welcome to *IFSC Finder | PMetroMart*!\n\n"
        "कृपया अपना State लिखें:\n\n"
        "🌐 Visit our website: [PMetroMart IFSC Portal](https://pmetromart.in/ifsc/)",
        parse_mode="Markdown"
    )
    return STATE

def help_command(update: Update, context: CallbackContext):
    update.message.reply_text(
        "ℹ️ *IFSC Finder Bot Help*\n\n"
        "1️⃣ /start - Bot शुरू करें\n"
        "2️⃣ State भेजें (जैसे: Delhi)\n"
        "3️⃣ Branch भेजें (जैसे: Connaught)\n"
        "➡️ फिर Bot आपको IFSC details देगा।\n\n"
        "🌐 Visit website: [PMetroMart IFSC](https://pmetromart.in/ifsc/)",
        parse_mode="Markdown"
    )

# ✅ Hi / Hello Handler
def greet_user(update: Update, context: CallbackContext):
    return start(update, context)

def get_state(update: Update, context: CallbackContext):
    user_state = update.message.text.strip()
    context.user_data["state"] = user_state
    logger.info(f"DEBUG: User Input -> State={user_state}")
    update.message.reply_text("✅ State मिल गया!\nअब कृपया Branch का नाम भेजें:")
    return BRANCH

def get_branch(update: Update, context: CallbackContext):
    user_branch = update.message.text.strip()
    state = context.user_data.get("state")
    logger.info(f"DEBUG: User Input -> Branch={user_branch}, State={state}")

    # Typing action दिखाना
    context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    df, suggestions = search_ifsc(state, user_branch)

    # ✅ Log Query
    log_query(update.message.from_user, state, user_branch, len(df))

    if df.empty:
        if suggestions:
            update.message.reply_text(
                f"❌ Exact result नहीं मिला।\n👉 Suggestions: {', '.join(suggestions)}"
            )
        else:
            update.message.reply_text("❌ कोई result नहीं मिला।\nकृपया सही State/Branch नाम डालें।")
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
            update.message.reply_text(msg, parse_mode="Markdown")

        update.message.reply_text(
            "✅ Search पूरा हुआ।\nफिर से शुरू करने के लिए /start दबाएँ।\n\n"
            "🌐 More info: [PMetroMart IFSC Portal](https://pmetromart.in/ifsc/)",
            parse_mode="Markdown"
        )

    return ConversationHandler.END

def cancel(update: Update, context: CallbackContext):
    update.message.reply_text("❌ Operation cancel कर दिया गया।")
    return ConversationHandler.END

# ✅ Timeout Handler
def timeout_handler(update: Update, context: CallbackContext):
    update.message.reply_text(
        "⌛ समय समाप्त!\nहमको आपका जवाब नहीं मिला।\nकृपया /start से फिर से कोशिश करें।"
    )
    return ConversationHandler.END

# ================== Main Function ==================
def main():
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            STATE: [MessageHandler(Filters.text & ~Filters.command, get_state)],
            BRANCH: [MessageHandler(Filters.text & ~Filters.command, get_branch)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        conversation_timeout=60  # 1 min timeout
    )

    dp.add_handler(conv_handler)
    dp.add_handler(CommandHandler("help", help_command))

    # hi/hello greet handler
    greet_handler = MessageHandler(
        Filters.regex(r'^(hi|hello|hii|hey|namaste)$') & ~Filters.command,
        greet_user
    )
    dp.add_handler(greet_handler)

    updater.start_polling()
    logger.info("✅ Bot started and polling Telegram...")
    updater.idle()

if __name__ == "__main__":
    main()
