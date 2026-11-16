import os
import random
import asyncio
import logging
import threading
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pymongo import MongoClient
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
PRIVATE_GROUP_LINK = os.getenv("PRIVATE_GROUP_LINK", "https://t.me")
MONGO_URL = os.getenv("MONGO_URL", "")

logging.basicConfig(level=logging.INFO)

# --- MONGODB CONNECTION ---
mongo_client = MongoClient(MONGO_URL)
db = mongo_client["nocturne_elite"]
users_col = db["builders"]

Q1_FOCUS, Q2_STAGE, Q3_GOAL, Q4_SKILL, Q5_COMMITMENT = range(5)


# --- TINY KEEP-ALIVE WEB SERVER ---
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Nocturne Elite Phase 2 is running 24/7.")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()


def start_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()


def is_low_effort(text: str) -> bool:
    cleaned = text.strip().lower()
    spam_words = {"idk", "nothing", "none", "asdf", "test", "hi", "hello", "no", "yes", "ok"}
    return len(cleaned) < 4 or cleaned in spam_words


def format_builder_card(data: dict) -> str:
    return (
        f"🏛️ **NOCTURNE ELITE — BUILDER CARD**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 **Builder:** {data['first_name']}\n"
        f"🎯 **Core Focus:** {data['focus']}\n"
        f"📈 **Current Stage:** {data['stage']}\n"
        f"⚡ **30-Day Mission:** {data['goal']}\n"
        f"🛠️ **Key Edge:** {data['skill']}\n"
        f"🤝 **Commitment & Ideal Peer:** {data['commitment']}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )


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

    builder_doc = {
        "user_id": user.id,
        "first_name": user.first_name,
        "username": user.username or "",
        "focus": context.user_data["focus"],
        "stage": context.user_data["stage"],
        "goal": context.user_data["goal"],
        "skill": context.user_data["skill"],
        "commitment": text,
        "status": "pending",
        "current_partner_id": None,
        "past_partners": [],
        "updated_at": datetime.now(timezone.utc),
    }

    users_col.update_one({"user_id": user.id}, {"$set": builder_doc}, upsert=True)
    card = format_builder_card(builder_doc)

    await update.message.reply_text(
        f"✅ **Your Builder Profile is Saved Permanently!**\n\n{card}\n\n"
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
        chat_id=OWNER_ID,
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
        users_col.update_one({"user_id": target_id}, {"$set": {"status": "approved"}})
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
            await query.edit_message_text(f"{query.message.text}\n\n⚠️ Approved in DB, but could not DM user: {e}")

    elif action == "reject":
        users_col.update_one({"user_id": target_id}, {"$set": {"status": "rejected"}})
        await query.edit_message_text(f"{query.message.text}\n\n❌ **REJECTED by Founder.**", parse_mode="Markdown")


async def view_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    doc = users_col.find_one({"user_id": update.effective_user.id})
    if not doc:
        await update.message.reply_text("You don't have a Builder Profile yet. Send /start to create one.")
    else:
        status_badge = doc.get("status", "pending").upper()
        await update.message.reply_text(
            f"{format_builder_card(doc)}\n\n📌 **Membership Status:** `{status_badge}`",
            parse_mode="Markdown",
        )


async def view_match(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    doc = users_col.find_one({"user_id": update.effective_user.id})
    if not doc or doc.get("status") != "approved":
        await update.message.reply_text("🔒 Weekly matching is open to approved Nocturne Elite members. Complete /start first.")
        return

    partner_id = doc.get("current_partner_id")
    if not partner_id:
        await update.message.reply_text(
            "⏳ **No active match yet this cycle.**\n"
            "You are in the active pool! You will receive a DM as soon as the Founder triggers the next matching round.",
            parse_mode="Markdown",
        )
        return

    partner = users_col.find_one({"user_id": partner_id})
    if not partner:
        await update.message.reply_text("Your partner's profile could not be found. Wait for the next round.")
        return

    handle = f"@{partner['username']}" if partner.get("username") else f"[Message Partner](tg://user?id={partner['user_id']})"
    await update.message.reply_text(
        f"🤝 **Your Current Accountability Partner:** {partner['first_name']} ({handle})\n\n"
        f"{format_builder_card(partner)}\n\n"
        "💡 *Reach out today, share your 30-day goal, and set a weekly check-in time.*",
        parse_mode="Markdown",
    )


async def run_matches(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != OWNER_ID:
        return

    approved = list(users_col.find({"status": "approved"}))
    if len(approved) < 2:
        await update.message.reply_text(f"⚠️ Need at least 2 approved builders to run matches (currently {len(approved)}).")
        return

    random.shuffle(approved)
    approved.sort(key=lambda x: x.get("stage", ""))

    paired_count = 0
    for i in range(0, len(approved) - 1, 2):
        b1 = approved[i]
        b2 = approved[i + 1]

        users_col.update_one(
            {"user_id": b1["user_id"]},
            {"$set": {"current_partner_id": b2["user_id"]}, "$addToSet": {"past_partners": b2["user_id"]}},
        )
        users_col.update_one(
            {"user_id": b2["user_id"]},
            {"$set": {"current_partner_id": b1["user_id"]}, "$addToSet": {"past_partners": b1["user_id"]}},
        )

        for person, match in [(b1, b2), (b2, b1)]:
            handle = f"@{match['username']}" if match.get("username") else f"[Direct Link](tg://user?id={match['user_id']})"
            try:
                await context.bot.send_message(
                    chat_id=person["user_id"],
                    text=(
                        f"⚡ **New Nocturne Elite Match Dropped!**\n\n"
                        f"You have been paired with **{match['first_name']}** ({handle}) for this sprint.\n\n"
                        f"{format_builder_card(match)}\n\n"
                        "🚀 *Send them a message today to align on your 30-day missions.*"
                    ),
                    parse_mode="Markdown",
                )
            except Exception as e:
                logging.error(f"Failed to notify {person['user_id']}: {e}")

        paired_count += 2

    leftover = "\n*(1 builder waited this round due to odd member count.)*" if len(approved) % 2 == 1 else ""
    await update.message.reply_text(
        f"✅ **Matchmaking Complete!** Paired **{paired_count}** builders and sent their intros.{leftover}",
        parse_mode="Markdown",
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != OWNER_ID:
        return
    total = users_col.count_documents({})
    approved = users_col.count_documents({"status": "approved"})
    pending = users_col.count_documents({"status": "pending"})
    await update.message.reply_text(
        f"📊 **Nocturne Elite Network Stats**\n"
        f"• Total Applications: **{total}**\n"
        f"• Approved Builders: **{approved}**\n"
        f"• Pending Review: **{pending}**",
        parse_mode="Markdown",
    )


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != OWNER_ID:
        return
    msg = " ".join(context.args)
    if not msg:
        await update.message.reply_text("Usage: `/broadcast Your announcement text here`", parse_mode="Markdown")
        return

    approved = list(users_col.find({"status": "approved"}))
    sent = 0
    for user in approved:
        try:
            await context.bot.send_message(
                chat_id=user["user_id"],
                text=f"📣 **Nocturne Elite Dispatch**\n\n{msg}",
                parse_mode="Markdown",
            )
            sent += 1
        except Exception:
            pass
    await update.message.reply_text(f"✅ Broadcast delivered to **{sent}/{len(approved)}** approved builders.", parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "**How Nocturne Elite Works:**\n"
        "1. Complete the 5-question interview via /start.\n"
        "2. View your saved card anytime with /profile.\n"
        "3. Check your active accountability partner via /match."
    )
    if update.effective_user.id == OWNER_ID:
        text += (
            "\n\n👑 **Founder Commands:**\n"
            "• `/run_matches` — Pair approved builders & send intros\n"
            "• `/stats` — View network numbers\n"
            "• `/broadcast <msg>` — Message all approved members"
        )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Onboarding cancelled. Type /start anytime to begin again.")
    return ConversationHandler.END


def main() -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    threading.Thread(target=start_health_server, daemon=True).start()
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
    app.add_handler(CommandHandler("match", view_match))
    app.add_handler(CommandHandler("run_matches", run_matches))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("help", help_command))

    print("Nocturne Elite Phase 2 is live...")
    app.run_polling()


if __name__ == "__main__":
    main()


