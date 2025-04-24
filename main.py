import os
import time
import asyncio
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, 
    filters, CallbackQueryHandler, ContextTypes
)

# Configuration
TOKEN = os.environ.get("TOKEN")
if not TOKEN:
    raise ValueError("Missing required environment variable: TOKEN")

CHAT_ID = os.environ.get("CHAT_ID", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
CONNECTION_TIMEOUT = 45  # seconds

# Global state
class ChatState:
    def __init__(self):
        self.waiting_user = None
        self.connections = {}
        self.all_users = set()
        self.waiting_start_time = None

chat_state = ChatState()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command"""
    user_id = update.effective_user.id
    chat_state.all_users.add(user_id)
    await update.message.reply_text(
        "\U0001F310 Welcome to *Anonymous Chat Bot*! \U0001F310\n"
        "Stay anonymous and connect with new people!\n"
        "Use /connect to meet someone or /invite to bring friends! \U0001F60E",
        parse_mode='Markdown'
    )

async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /connect command"""
    user_id = update.effective_user.id
    chat_state.all_users.add(user_id)

    if user_id in chat_state.connections:
        await update.message.reply_text("⚠️ You're already chatting! Use /disconnect first.")
        return

    if chat_state.waiting_user == user_id:
        await update.message.reply_text("⏳ You're already in the queue. Please wait...")
        return

    if chat_state.waiting_user is None:
        chat_state.waiting_user = user_id
        chat_state.waiting_start_time = time.time()
        await update.message.reply_text("⌛ Looking for a partner...")
    else:
        partner_id = chat_state.waiting_user
        chat_state.connections[user_id] = partner_id
        chat_state.connections[partner_id] = user_id
        await context.bot.send_message(partner_id, "✅ Connected! Say hi!")
        await update.message.reply_text("✅ Connected! Start chatting!")
        chat_state.waiting_user = None
        chat_state.waiting_start_time = None

async def disconnect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /disconnect command"""
    user_id = update.effective_user.id
    if user_id in chat_state.connections:
        partner_id = chat_state.connections[user_id]
        del chat_state.connections[user_id]
        if partner_id in chat_state.connections:
            del chat_state.connections[partner_id]
            try:
                await context.bot.send_message(
                    partner_id,
                    "🚪 Your partner left. Use /connect to meet someone new!"
                )
            except Exception:
                pass
        await update.message.reply_text("✅ You left the chat.")
    else:
        await update.message.reply_text("❌ You're not currently in a chat.")

async def invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /invite command"""
    if not CHAT_ID:
        await update.message.reply_text("❌ Group chat not configured")
        return

    user_id = update.effective_user.id
    chat_state.all_users.add(user_id)
    try:
        invite_link = await context.bot.export_chat_invite_link(chat_id=CHAT_ID)
        await update.message.reply_text(
            f"📨 Invite friends to our *Anonymous Chat*!\n"
            f"Join here: {invite_link}",
            parse_mode='Markdown'
        )
    except Exception as e:
        await update.message.reply_text("❌ Couldn't generate invite link.")
        print(f"Invite error: {e}")

async def forward_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Forward messages between connected users"""
    user_id = update.effective_user.id
    chat_state.all_users.add(user_id)
    if user_id in chat_state.connections:
        partner_id = chat_state.connections[user_id]
        try:
            await context.bot.send_message(partner_id, f"💬 {update.message.text}")
        except Exception:
            await update.message.reply_text("❌ Message failed to send.")
            await disconnect(update, context)
    else:
        await update.message.reply_text("❌ You're not in a chat.")

async def reveal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /reveal command"""
    user_id = update.effective_user.id
    if user_id in chat_state.connections:
        partner_id = chat_state.connections[user_id]
        keyboard = [
            [
                InlineKeyboardButton("Yes ✅", callback_data=f"reveal_yes_{user_id}"),
                InlineKeyboardButton("No ❌", callback_data=f"reveal_no_{user_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await context.bot.send_message(
                partner_id,
                "🤔 Your partner wants to reveal their identity. Agree?",
                reply_markup=reply_markup
            )
            await update.message.reply_text("⏳ Waiting for response...")
        except Exception:
            await update.message.reply_text("❌ Couldn't send request.")
    else:
        await update.message.reply_text("❌ You're not connected.")

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
    query = update.callback_query
    await query.answer()
    data = query.data
    parts = data.split('_')
    action = parts[0] + '_' + parts[1]
    user_id = int(parts[-1])
    partner_id = query.from_user.id

    if action == "reveal_yes" and chat_state.connections.get(partner_id) == user_id:
        try:
            user_info = await context.bot.get_chat(user_id)
            partner_info = await context.bot.get_chat(partner_id)
            user_name = user_info.full_name or "Anonymous"
            await context.bot.send_message(partner_id, f"🎉 Your partner is {user_name}.")
            await query.edit_message_text("✅ Identities revealed!")
        except Exception:
            await query.edit_message_text("❌ Failed to reveal.")

    elif action == "reveal_no" and chat_state.connections.get(partner_id) == user_id:
        try:
            await context.bot.send_message(user_id, "🙁 Your partner declined.")
            await query.edit_message_text("❌ Request declined.")
        except Exception:
            await query.edit_message_text("❌ Couldn't send response.")

    elif data == "try_again":
        chat_state.waiting_user = None
        chat_state.waiting_start_time = None
        try:
            await connect(update, context)
            await query.edit_message_text("🔄 Trying again...")
        except Exception:
            await query.edit_message_text("❌ Failed to reconnect.")

async def check_timeout(context: ContextTypes.DEFAULT_TYPE):
    """Check for waiting users who have timed out"""
    if (chat_state.waiting_user is not None and 
        chat_state.waiting_start_time is not None and 
        time.time() - chat_state.waiting_start_time > CONNECTION_TIMEOUT):
        
        keyboard = [[InlineKeyboardButton("Try Again 🔄", callback_data="try_again")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await context.bot.send_message(
                chat_state.waiting_user,
                "⏰ No partner found. Try again?",
                reply_markup=reply_markup
            )
        except Exception:
            pass
        chat_state.waiting_user = None
        chat_state.waiting_start_time = None

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin broadcast command"""
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ Admin only!")
        return

    message = " ".join(context.args)
    if not message:
        await update.message.reply_text("⚠️ Usage: /broadcast <message>")
        return

    success = 0
    for uid in chat_state.all_users:
        try:
            await context.bot.send_message(uid, f"📢 *Admin:* {message}", parse_mode='Markdown')
            success += 1
        except Exception:
            continue
    
    await update.message.reply_text(f"✅ Sent to {success} users.")

async def run_bot():
    """Run the bot application"""
    application = None
    try:
        application = ApplicationBuilder().token(TOKEN).build()

        # Register handlers
        handlers = [
            CommandHandler("start", start),
            CommandHandler("connect", connect),
            CommandHandler("disconnect", disconnect),
            CommandHandler("invite", invite),
            CommandHandler("reveal", reveal),
            CommandHandler("broadcast", broadcast),
            CallbackQueryHandler(button),
            MessageHandler(filters.TEXT & ~filters.COMMAND, forward_message)
        ]
        
        for handler in handlers:
            application.add_handler(handler)

        # Initialize application
        await application.initialize()
        await application.start()
        
        # Start background tasks
        if hasattr(application, 'job_queue') and application.job_queue is not None:
            application.job_queue.run_repeating(check_timeout, interval=5.0)
            print("✅ Timeout checker started")

        print("🚀 Bot is running...")
        await application.run_polling()

    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if application is not None:
            try:
                await application.stop()
                await application.shutdown()
            except Exception:
                pass

def main():
    """Entry point for the application"""
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped")
    except Exception as e:
        print(f"❌ Fatal error: {e}")

if __name__ == '__main__':
    main()
