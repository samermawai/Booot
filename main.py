import os
import logging
import time
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ContextTypes
)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
CHAT_ID = os.getenv("CHAT_ID", "")
WEB_PORT = int(os.getenv("PORT", 8000))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
CONNECTION_TIMEOUT = 45  # seconds

class ChatManager:
    def __init__(self):
        self.waiting_user = None
        self.connections = {}
        self.users = set()
        self.waiting_start_time = None

chat_manager = ChatManager()

# ======================
# Command Handlers
# ======================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_manager.users.add(user_id)
    await update.message.reply_text(
        "🔒 *Anonymous Chat Bot*\n"
        "Use /connect to start chatting!\n"
        "/reveal to request identity disclosure\n"
        "/invite to get group link",
        parse_mode="Markdown"
    )

async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_manager.users.add(user_id)

    if user_id in chat_manager.connections:
        await update.message.reply_text("⚠️ You're already in a chat! Use /disconnect first.")
        return

    if chat_manager.waiting_user:
        partner_id = chat_manager.waiting_user
        chat_manager.connections[user_id] = partner_id
        chat_manager.connections[partner_id] = user_id
        chat_manager.waiting_user = None
        chat_manager.waiting_start_time = None
        
        await context.bot.send_message(partner_id, "✅ Connected! Chat anonymously now!")
        await update.message.reply_text("✅ Connected! Start chatting!")
    else:
        chat_manager.waiting_user = user_id
        chat_manager.waiting_start_time = time.time()
        await update.message.reply_text("🔍 Searching for a partner...")

async def disconnect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in chat_manager.connections:
        partner_id = chat_manager.connections[user_id]
        del chat_manager.connections[user_id]
        if partner_id in chat_manager.connections:
            del chat_manager.connections[partner_id]
            await context.bot.send_message(partner_id, "🚪 Partner disconnected")
        await update.message.reply_text("✅ Disconnected successfully")
    else:
        await update.message.reply_text("❌ You're not in an active chat")

async def reveal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in chat_manager.connections:
        await update.message.reply_text("❌ You're not in a chat")
        return

    partner_id = chat_manager.connections[user_id]
    keyboard = [
        [
            InlineKeyboardButton("Accept ✅", callback_data=f"reveal_yes_{user_id}"),
            InlineKeyboardButton("Decline ❌", callback_data=f"reveal_no_{user_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await context.bot.send_message(
            partner_id,
            "🔓 Your partner wants to reveal their identity. Allow?",
            reply_markup=reply_markup
        )
        await update.message.reply_text("⏳ Reveal request sent...")
    except Exception as e:
        await update.message.reply_text("❌ Failed to send request")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ Admin only command!")
        return

    if not context.args:
        await update.message.reply_text("Usage: /broadcast <message>")
        return

    message = " ".join(context.args)
    success = 0
    for uid in chat_manager.users:
        try:
            await context.bot.send_message(uid, f"📢 *Admin Broadcast:* {message}", parse_mode="Markdown")
            success += 1
        except Exception:
            continue
    
    await update.message.reply_text(f"✅ Broadcast sent to {success} users")

async def invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not CHAT_ID:
        await update.message.reply_text("❌ Group chat not configured")
        return

    try:
        invite_link = await context.bot.export_chat_invite_link(int(CHAT_ID))
        await update.message.reply_text(
            f"👥 Join our community:\n{invite_link}\n"
            "Share this link to invite friends!"
        )
    except Exception as e:
        await update.message.reply_text("❌ Failed to generate invite link")
        logger.error(f"Invite error: {e}")

# ======================
# Message Handling
# ======================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in chat_manager.connections:
        await update.message.reply_text("❌ You're not connected. Use /connect first")
        return

    partner_id = chat_manager.connections[user_id]
    try:
        await context.bot.send_message(partner_id, f"💬 {update.message.text}")
    except Exception:
        await update.message.reply_text("❌ Message failed to send")
        await disconnect(update, context)

# ======================
# Callback Handlers
# ======================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("_")
    action = f"{data[0]}_{data[1]}"
    user_id = int(data[2])
    partner_id = query.from_user.id

    if action == "reveal_yes":
        try:
            user = await context.bot.get_chat(user_id)
            await context.bot.send_message(partner_id, f"👤 Partner's name: {user.full_name}")
            await context.bot.send_message(user_id, "✅ Identity revealed successfully!")
            await query.edit_message_text("✅ Identity shared")
        except Exception:
            await query.edit_message_text("❌ Failed to reveal identity")

    elif action == "reveal_no":
        await context.bot.send_message(user_id, "❌ Partner declined identity reveal")
        await query.edit_message_text("🚫 Request declined")

# ======================
# System Functions
# ======================

async def check_timeout(context: ContextTypes.DEFAULT_TYPE):
    if chat_manager.waiting_user and (time.time() - chat_manager.waiting_start_time > CONNECTION_TIMEOUT):
        await context.bot.send_message(
            chat_manager.waiting_user,
            "⏰ Connection timeout. Use /connect to try again"
        )
        chat_manager.waiting_user = None
        chat_manager.waiting_start_time = None

def setup_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("connect", connect))
    app.add_handler(CommandHandler("disconnect", disconnect))
    app.add_handler(CommandHandler("reveal", reveal))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("invite", invite))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))

async def run_bot():
    app = ApplicationBuilder().token(TOKEN).build()
    setup_handlers(app)
    
    # Setup webhook for Render
    if WEBHOOK_URL:
        await app.bot.set_webhook(
            url=f"{WEBHOOK_URL}/webhook",
            secret_token=os.getenv("WEBHOOK_SECRET")
        )
        logger.info("Webhook configured")
    else:
        logger.info("Running in polling mode")

    # Start background tasks
    app.job_queue.run_repeating(check_timeout, interval=30)

    # Start the bot
    await app.initialize()
    await app.start()
    logger.info("Bot started successfully")
    
    # Keep the application running
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    if not TOKEN:
        raise ValueError("Missing TOKEN environment variable")
    
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
