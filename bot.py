import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# --- CONFIGURATION ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
OWNER_ID = int(os.getenv("OWNER_ID", "123456789"))
LOGGER_ID = int(os.getenv("LOGGER_ID", "-1001234567890"))
PRIVATE_GROUP_LINK = os.getenv("PRIVATE_GROUP_LINK", "https://t.me")

logging.basicConfig(level=logging.INFO)

Q1_FOCUS, Q2_STAGE, Q3_GOAL, Q4_SKILL, Q5_COMMITMENT = range(5)
PROFILES = {}


def is_low_effort(text: str) -> bool:
    cleaned = text.strip().lower()
    spam_words = {"idk", "nothing", "none", "asdf", "test", "hi", "hello", "no", "yes", "ok"}
    return len(cleaned) < 4 or cleaned in spam_words


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    welcome_text = (
        f"🔥 **Welcome to Nocturne Elite, {user.first_name}.**\n\n"
        "This is a curated matchmaking and accountability network for serious builders, "
        "creators, and founders.\n\n"
        "Complete this 5-question onboarding interview to generate your Builder Profile "
        "and apply for weekly partner matching.\n\n"
        "**Question 1 of 5:**\n"
        "What are you actively building, studying, or mastering right now?\n"
        "*(e.g., Coding/AI, Design, Content Creation, Startups, Finance)*"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")
    return Q1_FOCUS


async def get_q1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if is_low_effort(text):
        await update.message.reply_text("⚠️ Please give a real answer so we can match you properly. What are you building or mastering?")
        return Q1_FOCUS
    context.user_data["focus"] = text
    keyboard = [
        [
            InlineKeyboardButton("🌱 Just Starting", callback_data="Just Starting"),
            InlineKeyboardButton("🛠️ Building First Project", callback_data="Building First Project"),
        ],
        [
            InlineKeyboardButton("💼 Freelancing / Earning", callback_data="Freelancing / Earning"),
            InlineKeyboardButton("🚀 Scaling a Brand/Product", callback_data="Scaling"),
        ],
    ]
    await update.message.reply_text(
        "**Question 2 of 5:**\nWhere are you currently on your journey?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )
    return Q2_STAGE


async def get_q2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["stage"] = query.data
    await query.edit_message_text(
        f"Stage selected: **{query.data}**\n\n"
        "**Question 3 of 5:**\n"
        "What is your #1 concrete goal for the next 30 days?",
        parse_mode="Markdown",
    )
    return Q3_GOAL


async def get_q3(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if is_low_effort(text):
        await update.message.reply_text("⚠️ Please share a specific 30-day goal (at least a few words).")
        return Q3_GOAL
    context.user_data["goal"] = text
    await update.message.reply_text(
        "**Question 4 of 5:**\n"
        "What specific skill, strength, or mindset do you bring to a teammate or accountability partner?",
        parse_mode="Markdown",
    )
    return Q4_SKILL


async def get_q4(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if is_low_effort(text):
        await update.message.reply_text("⚠️ Tell us a bit more about what skill or energy you bring to a team.")
        return Q4_SKILL
    context.user_data["skill"] = text
    await update.message.reply_text(
        "**Question 5 of 5:**\n"
        "How many hours per week do you dedicate to your craft, and what kind of peer do you want to meet?",
        parse_mode="Markdown",
    )
    return Q5_COMMITMENT


async def get_q5(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    text = update.message.text.strip()
    if is_low_effort(text):
        await update.message.reply_text("⚠️ Please share your weekly hours and ideal partner type.")
        return Q5_COMMITMENT

    context.user_data["commitment"] = text

    # Build Executive Builder Card
    card = (
        f"🏛️ **NOCTURNE ELITE — BUILDER CARD**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 **Builder:** {user.first_name}\n"
        f"🎯 **Core Focus:** {context.user_data['focus']}\n"
        f"📈 **Current Stage:** {context.user_data['stage']}\n"
        f"⚡ **30-Day Mission:** {context.user_data['goal']}\n"
        f"🛠️ **Key Edge:** {context.user_data['skill']}\n"
        f"🤝 **Commitment & Ideal Peer:** {context.user_data['commitment']}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )

    PROFILES[user.id] = card

    await update.message.reply_text(
        f"✅ **Your Builder Profile is Live!**\n\n{card}\n\n"
        "🔎 *Your profile has been sent for founder review. You will be notified once approved for weekly matching.*",
        parse_mode="Markdown",
    )

    admin_buttons = [
        [
            InlineKeyboardButton("✅ Approve & Send Invite", callback_data=f"approve_{user.id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user.id}"),
        ]
    ]
    admin_caption = (
        f"📥 **New Nocturne Elite Application**\n"
        f"Handle: @{user.username or 'NoUsername'} | ID: `{user.id}`\n\n"
        f"{card}"
    )
    await context.bot.send_message(
        chat_id=LOGGER_ID,
        text=admin_caption,
        reply_markup=InlineKeyboardMarkup(admin_buttons),
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def admin_decision(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.from_user.id != OWNER_ID:
        await query.answer("Only the Founder can approve applications.", show_alert=True)
        return

    action, target_id_str = query.data.split("_")
    target_id = int(target_id_str)

    if action == "approve":
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=(
                    "🔥 **You Have Been Accepted into Nocturne Elite.**\n\n"
                    "Your Builder Profile passed review. You are now active in our weekly matchmaking pool.\n\n"
                    f"🗝️ **Private Builders Circle:** {PRIVATE_GROUP_LINK}\n"
                    "*(Do not share this invite link with anyone.)*"
                ),
                parse_mode="Markdown",
            )
            await query.edit_message_text(f"{query.message.text}\n\n✅ **APPROVED by Founder.**", parse_mode="Markdown")
        except Exception as e:
            await query.edit_message_text(f"{query.message.text}\n\n⚠️ Could not DM user: {e}")

    elif action == "reject":
        await query.edit_message_text(f"{query.message.text}\n\n❌ **REJECTED by Founder.**", parse_mode="Markdown")


async def view_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    profile = PROFILES.get(update.effective_user.id)
    if not profile:
        await update.message.reply_text("You don't have a Builder Profile yet. Send /start to create one.")
    else:
        await update.message.reply_text(profile, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "**How Nocturne Elite Works:**\n"
        "1. Complete the 5-question interview via /start.\n"
        "2. Generate your executive Builder Card.\n"
        "3. Approved members unlock our private circle and get paired weekly with compatible peers.",
        parse_mode="Markdown",
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Onboarding cancelled. Type /start anytime to begin again.")
    return ConversationHandler.END


def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            Q1_FOCUS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_q1)],
            Q2_STAGE: [CallbackQueryHandler(get_q2)],
            Q3_GOAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_q3)],
            Q4_SKILL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_q4)],
            Q5_COMMITMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_q5)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(admin_decision, pattern="^(approve|reject)_"))
    app.add_handler(CommandHandler("profile", view_profile))
    app.add_handler(CommandHandler("help", help_command))

    print("Nocturne Elite Bot is live...")
    app.run_polling()


if __name__ == "__main__":
    main()
