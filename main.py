import os
import random
import time
import asyncio
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
)
# Upar import section me add hona chahiye

TOKEN = os.environ.get("TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
 # Replace with your Telegram user ID

# User management
waiting_user = None
connections = {}
all_users = set()
waiting_start_time = None

# Start Command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    all_users.add(user_id)
    await update.message.reply_text(
        "\U0001F310 Welcome to *Anonymous Chat Bot*! \U0001F310\n"
        "Stay anonymous and connect with new people!\nUse /connect to meet someone or /invite to bring your friends along! \U0001F60E",
        parse_mode='Markdown'
    )

# Connect Command
async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global waiting_user, waiting_start_time
    user_id = update.effective_user.id
    all_users.add(user_id)

    if user_id in connections:
        await update.message.reply_text("⚠️ You're already chatting! Use /disconnect to end your current chat. 😶")
        return

    if waiting_user == user_id:
        await update.message.reply_text("⏳ You're already in the queue. Please wait to be connected... 🕒")
        return

    if waiting_user is None:
        waiting_user = user_id
        waiting_start_time = time.time()
        await update.message.reply_text("⌛ Looking for a partner... Sit tight! 🧘")
    else:
        if waiting_user == user_id:
            await update.message.reply_text("❌ You can't connect with yourself! Be patient. 😅")
            return
        partner_id = waiting_user
        connections[user_id] = partner_id
        connections[partner_id] = user_id
        await context.bot.send_message(partner_id, "✅ You've been connected! Say hi to your new friend! 💬")
        await update.message.reply_text("✅ You've been connected! Enjoy your chat! 💬")
        waiting_user = None
        waiting_start_time = None

# Disconnect Command
async def disconnect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in connections:
        partner_id = connections[user_id]
        del connections[user_id]
        del connections[partner_id]
        await context.bot.send_message(partner_id, "🚪 Your partner has left the chat. Use /connect to meet someone new!")
        await update.message.reply_text("✅ You left the chat. Use /connect to find a new partner.")
    else:
        await update.message.reply_text("❌ You're not currently in a chat.")

# Invite Command
async def invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    all_users.add(user_id)
    try:
        invite_link = await context.bot.export_chat_invite_link(chat_id=CHAT_ID)
        await update.message.reply_text(
            f"📨 Invite your friends to the *Anonymous Chat Community*!\n"
            f"Click here to join: {invite_link}\nMore users = more fun! 🎉",
            parse_mode='Markdown'
        )
    except Exception as e:
        await update.message.reply_text("❌ Can't generate invite link. Make sure the bot is an admin.")
        print(f"Invite error: {e}")

# Message Forwarding
async def forward_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    all_users.add(user_id)
    if user_id in connections:
        partner_id = connections[user_id]
        await context.bot.send_message(partner_id, f"💬 {update.message.text}")
    else:
        await update.message.reply_text("❌ You're not in a chat. Use /connect to start chatting.")

# Reveal Identity
async def reveal(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await context.bot.send_message(partner_id, "🤔 Your partner wants to reveal their identity. Do you agree?", reply_markup=reply_markup)
        await update.message.reply_text("⏳ Waiting for your partner's response...")
    else:
        await update.message.reply_text("❌ You're not connected. Use /connect to start chatting.")

# Handle Button Clicks
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global waiting_user, waiting_start_time
    query = update.callback_query
    await query.answer()
    data = query.data
    parts = data.split('_')
    action = parts[0] + '_' + parts[1]
    user_id = int(parts[-1])
    partner_id = query.from_user.id

    if action == "reveal_yes" and connections.get(partner_id) == user_id:
        user_info = await context.bot.get_chat(user_id)
        partner_info = await context.bot.get_chat(partner_id)

        user_name = user_info.full_name or "Anonymous"
        partner_name = partner_info.full_name or "Anonymous"

        await context.bot.send_message(partner_id, f"🎉 Identity revealed! Your partner is {user_name}.")
        await context.bot.send_message(user_id, f"🎉 Identity revealed! Your partner is {partner_name}.")
        await query.edit_message_text("✅ Identity successfully revealed! 🎊")

    elif action == "reveal_no" and connections.get(partner_id) == user_id:
        await context.bot.send_message(user_id, "🙁 Your partner declined the reveal request.")
        await query.edit_message_text("❌ Reveal request declined.")

    elif data == "try_again":
        waiting_user = None
        waiting_start_time = None
        await connect(update, context)
        await query.edit_message_text("🔄 Trying to connect again... Please wait ⌛")

# Timeout Checker
async def check_timeout(context: ContextTypes.DEFAULT_TYPE):
    global waiting_user, waiting_start_time
    if waiting_user is not None and time.time() - waiting_start_time > 45:
        keyboard = [[InlineKeyboardButton("Try Again 🔄", callback_data="try_again")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(waiting_user, "⏰ No user found. Please try again or invite friends to join!", reply_markup=reply_markup)
        waiting_user = None
        waiting_start_time = None

# Broadcast
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ Only the admin can use this command!")
        return

    message = " ".join(context.args)
    if not message:
        await update.message.reply_text("⚠️ Usage: /broadcast <your message here>")
        return

    for uid in all_users:
        try:
            await context.bot.send_message(uid, f"📢 *Admin Message:* {message}", parse_mode='Markdown')
        except Exception as e:
            print(f"Failed to send to {uid}: {e}")
    await update.message.reply_text("✅ Broadcast sent successfully! 📬")

# Main Function
async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("connect", connect))
    app.add_handler(CommandHandler("disconnect", disconnect))
    app.add_handler(CommandHandler("invite", invite))
    app.add_handler(CommandHandler("reveal", reveal))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), forward_message))

 async def post_init(app):
    app.job_queue.run_repeating(check_timeout, interval=5)

await app.initialize()
await post_init(app)
await app.start()
await app.updater.start_polling()
await app.updater.idle()

    print("🚀 Bot is running...")
    await app.run_polling()

if __name__ == '__main__':
    asyncio.run(main())
