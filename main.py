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
CHAT_ID = os.environ.get("CHAT_ID")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
CONNECTION_TIMEOUT = 45  # seconds

# Global state
waiting_user = None
connections = {}
all_users = set()
waiting_start_time = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command"""
    user_id = update.effective_user.id
    all_users.add(user_id)
    await update.message.reply_text(
        "\U0001F310 Welcome to *Anonymous Chat Bot*! \U0001F310\n"
        "Stay anonymous and connect with new people!\n"
        "Use /connect to meet someone or /invite to bring your friends along! \U0001F60E",
        parse_mode='Markdown'
    )

async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /connect command"""
    global waiting_user, waiting_start_time
    user_id = update.effective_user.id
    all_users.add(user_id)

    if user_id in connections:
        await update.message.reply_text("⚠️ You're already chatting! Use /disconnect first. 😶")
        return

    if waiting_user == user_id:
        await update.message.reply_text("⏳ You're already in the queue. Please wait... 🕒")
        return

    if waiting_user is None:
        waiting_user = user_id
        waiting_start_time = time.time()
        await update.message.reply_text("⌛ Looking for a partner... Sit tight! �")
    else:
        partner_id = waiting_user
        connections[user_id] = partner_id
        connections[partner_id] = user_id
        await context.bot.send_message(partner_id, "✅ Connected! Say hi to your new friend! 💬")
        await update.message.reply_text("✅ Connected! Enjoy your chat! 💬")
        waiting_user = None
        waiting_start_time = None

async def disconnect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /disconnect command"""
    user_id = update.effective_user.id
    if user_id in connections:
        partner_id = connections[user_id]
        del connections[user_id]
        if partner_id in connections:
            del connections[partner_id]
            try:
                await context.bot.send_message(
                    partner_id,
                    "🚪 Your partner left. Use /connect to meet someone new!"
                )
            except Exception:
                pass  # Partner might have blocked the bot
        await update.message.reply_text("✅ You left the chat. Use /connect to find a new partner.")
    else:
        await update.message.reply_text("❌ You're not currently in a chat.")

async def invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /invite command"""
    user_id = update.effective_user.id
    all_users.add(user_id)
    try:
        invite_link = await context.bot.export_chat_invite_link(chat_id=CHAT_ID)
        await update.message.reply_text(
            f"📨 Invite friends to our *Anonymous Chat Community*!\n"
            f"Join here: {invite_link}\nMore users = more fun! 🎉",
            parse_mode='Markdown'
        )
    except Exception as e:
        await update.message.reply_text("❌ Couldn't generate invite link. The bot needs admin rights.")
        print(f"Invite error: {e}")

async def forward_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Forward messages between connected users"""
    user_id = update.effective_user.id
    all_users.add(user_id)
    if user_id in connections:
        partner_id = connections[user_id]
        try:
            await context.bot.send_message(partner_id, f"💬 {update.message.text}")
        except Exception as e:
            print(f"Message forwarding error: {e}")
            await update.message.reply_text("❌ Message failed to send. Your partner may have disconnected.")
            await disconnect(update, context)  # Clean up the connection
    else:
        await update.message.reply_text("❌ You're not in a chat. Use /connect to start.")

async def reveal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /reveal command"""
    user_id = update.effective_user.id
    if user_id in connections:
        partner_id = connections[user_id]
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
                "🤔 Your partner wants to reveal their identity. Do you agree?",
                reply_markup=reply_markup
            )
            await update.message.reply_text("⏳ Waiting for your partner's response...")
        except Exception:
            await update.message.reply_text("❌ Couldn't send request. Your partner may have disconnected.")
    else:
        await update.message.reply_text("❌ You're not connected. Use /connect first.")

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
    global waiting_user, waiting_start_time
    query = update.callback_query
    await query.answer()
    data = query.data
    parts = data.split('_')
    action = parts[0] + '_' + parts[1]
    user_id = int(parts[-1])
    partner_id = query.from_user.id

    if action == "reveal_yes" and connections.get(partner_id) == user_id:
        try:
            user_info = await context.bot.get_chat(user_id)
            partner_info = await context.bot.get_chat(partner_id)

            user_name = user_info.full_name or "Anonymous"
            partner_name = partner_info.full_name or "Anonymous"

            await context.bot.send_message(partner_id, f"🎉 Your partner is {user_name}.")
            await context.bot.send_message(user_id, f"🎉 Your partner is {partner_name}.")
            await query.edit_message_text("✅ Identities revealed! 🎊")
        except Exception as e:
            print(f"Reveal error: {e}")
            await query.edit_message_text("❌ Failed to reveal identities.")

    elif action == "reveal_no" and connections.get(partner_id) == user_id:
        try:
            await context.bot.send_message(user_id, "🙁 Your partner declined the reveal request.")
            await query.edit_message_text("❌ Request declined.")
        except Exception:
            await query.edit_message_text("❌ Couldn't send response.")

    elif data == "try_again":
        waiting_user = None
        waiting_start_time = None
        try:
            await connect(update, context)
            await query.edit_message_text("🔄 Trying to connect again... ⌛")
        except Exception:
            await query.edit_message_text("❌ Failed to reconnect. Please try /connect.")

async def check_timeout(context: ContextTypes.DEFAULT_TYPE):
    """Check for waiting users who have timed out"""
    global waiting_user, waiting_start_time
    if (waiting_user is not None and 
        waiting_start_time is not None and 
        time.time() - waiting_start_time > CONNECTION_TIMEOUT):
        
        keyboard = [[InlineKeyboardButton("Try Again 🔄", callback_data="try_again")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await context.bot.send_message(
                waiting_user,
                "⏰ No partner found. Try again or invite friends!",
                reply_markup=reply_markup
            )
        except Exception as e:
            print(f"Timeout message error: {e}")
        waiting_user = None
        waiting_start_time = None

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin broadcast command"""
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ Admin only command!")
        return

    message = " ".join(context.args)
    if not message:
        await update.message.reply_text("⚠️ Usage: /broadcast <message>")
        return

    success, failed = 0, 0
    for uid in all_users:
        try:
            await context.bot.send_message(uid, f"📢 *Admin Message:* {message}", parse_mode='Markdown')
            success += 1
        except Exception as e:
            print(f"Failed to send to {uid}: {e}")
            failed += 1
    
    await update.message.reply_text(f"✅ Sent to {success} users. Failed: {failed}.")

async def main():
    """Main application setup"""
    if not TOKEN:
        print("❌ Error: Missing TOKEN environment variable!")
        return

    try:
        app = ApplicationBuilder().token(TOKEN).build()

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
            app.add_handler(handler)

        # Initialize and start
        await app.initialize()
        await app.start()
        
        # Start background tasks
        if hasattr(app, 'job_queue') and app.job_queue is not None:
            app.job_queue.run_repeating(check_timeout, interval=5.0)
            print("✅ Timeout checker started")
        else:
            print("⚠️ Job queue not available - timeout checker disabled")

        print("🚀 Bot is running...")
        await app.run_polling()

    except Exception as e:
        print(f"❌ Fatal error: {e}")
    finally:
        if 'app' in locals():
            await app.stop()
            await app.shutdown()

if __name__ == '__main__':
    asyncio.run(main())
