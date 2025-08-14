
import threading
from flask import Flask

app_flask = Flask(__name__)

@app_flask.route("/")
def home():
    return "Majbur bot ishlayapti!"

def run_web():
    app_flask.run(host="0.0.0.0", port=8080)

def start_web():
    threading.Thread(target=run_web).start()

import asyncio
import logging
import os
from collections import defaultdict

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand, BotCommandScopeAllPrivateChats, ChatPermissions
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters, ChatMemberHandler
)

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

TOKEN = os.getenv("TOKEN") or "YOUR_TOKEN_HERE"

# --------- Global holat ---------
MAJBUR_LIMIT = 0  # 0 => o'chirilgan
FOYDALANUVCHI_HISOBI = defaultdict(int)  # user_id -> qo'shgan odamlar soni

# --------- Admin/Owner aniqlash ---------
async def is_admin(update: Update) -> bool:
    chat = update.effective_chat
    user = update.effective_user
    if not (chat and user):
        return False
    try:
        member = await chat.get_member(user.id)
        return member.status in ("administrator", "creator")
    except Exception as e:
        logging.warning(f"is_admin tekshiruv xatoligi: {e}")
        return False

async def is_privileged_message(msg, bot) -> bool:
    """
    Creator/administrator va anonymous admin (sender_chat == chat.id) yozuvlarini aniqlash.
    """
    try:
        chat = msg.chat
        user = msg.from_user
        # Anonymous admin holati
        if getattr(msg, "sender_chat", None) and msg.sender_chat.id == chat.id:
            return True
        if user:
            member = await bot.get_chat_member(chat.id, user.id)
            if member.status in ("administrator", "creator"):
                return True
    except Exception as e:
        logging.warning(f"is_privileged_message xatoligi: {e}")
    return False

# --------- Inline klaviatura (/majbur uchun) ---------
def majbur_klaviatura():
    rows = [
        [10, 20, 30, 40, 50],
        [60, 70, 80, 90, 100],
    ]
    keyboard = [[InlineKeyboardButton(str(n), callback_data=f"set_limit:{n}") for n in row] for row in rows]
    keyboard.append([InlineKeyboardButton("❌ BEKOR QILISH ❌", callback_data="set_limit:cancel")])
    return InlineKeyboardMarkup(keyboard)

# --------- /start ---------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("➕ Guruhga qo‘shish", url=f"https://t.me/{context.bot.username}?startgroup=start")]]
    await update.message.reply_text(
        "<b>Salom👋</b>\n"
        "Men guruhingizda <b>majburiy odam qo‘shish</b> tizimini boshqaraman.\n\n"
        "Buyruqlar qo'llanmasi: /help\n\n"
        "Ishlashim uchun guruhingizga qo‘shib, <b>ADMIN</b> huquqi berishingiz kerak 🙂",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb)
    )

# --------- /help ---------
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📌 <b>Buyruqlar</b>\n\n"
        "🔹 <b>/majbur [son]</b> — Majburiy odam qo‘shish limitini o‘rnatish. Agar son yozilmasa, menyu chiqadi.\n"
        "🔹 <b>/majburoff</b> — Majburiy qo‘shishni o‘chirish.\n"
        "🔹 <b>/top</b> — Eng ko‘p qo‘shgan TOP 100.\n"
        "🔹 <b>/cleangroup</b> — Hamma hisobini 0 qilish.\n"
        "🔹 <b>/count</b> — Siz nechta odam qo‘shgansiz.\n"
        "🔹 <b>/replycount</b> — Reply qilingan foydalanuvchi hisobi.\n"
        "🔹 <b>/cleanuser</b> — Reply qilingan foydalanuvchi hisobini 0 qilish.\n"
    )
    await update.message.reply_text(text, parse_mode="HTML")

# --------- /majbur ---------
async def majbur(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("⛔ Bu komanda faqat adminlar uchun.")
        return
    global MAJBUR_LIMIT
    if context.args:
        try:
            val = int(context.args[0])
            if val < 0:
                raise ValueError
            MAJBUR_LIMIT = val
            await update.message.reply_text(f"✅ Majburiy odam qo‘shish limiti: <b>{MAJBUR_LIMIT}</b>", parse_mode="HTML")
        except ValueError:
            await update.message.reply_text("❌ Noto‘g‘ri qiymat. Masalan: <code>/majbur 10</code>", parse_mode="HTML")
    else:
        await update.message.reply_text(
            "👥 Guruhda majburiy odam qo‘shishni nechta qilib belgilay? 👇\nQo‘shish shart emas — /majburoff",
            reply_markup=majbur_klaviatura()
        )

# --------- Callback: set_limit ---------
async def on_set_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.callback_query.answer("Faqat adminlar!", show_alert=True)
        return
    query = update.callback_query
    await query.answer()
    data = query.data.split(":", 1)[1]
    global MAJBUR_LIMIT
    if data == "cancel":
        await query.edit_message_text("❌ Bekor qilindi.")
        return
    try:
        val = int(data)
        MAJBUR_LIMIT = val
        await query.edit_message_text(f"✅ Majburiy odam qo‘shish limiti: <b>{MAJBUR_LIMIT}</b>", parse_mode="HTML")
    except Exception:
        await query.edit_message_text("❌ Noto‘g‘ri qiymat.")

# --------- /majburoff ---------
async def majburoff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("⛔ Bu komanda faqat adminlar uchun.")
        return
    global MAJBUR_LIMIT
    MAJBUR_LIMIT = 0
    await update.message.reply_text("🚫 Majburiy odam qo‘shish o‘chirildi.")

# --------- /top ---------
async def top_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("⛔ Bu komanda faqat adminlar uchun.")
        return
    if not FOYDALANUVCHI_HISOBI:
        await update.message.reply_text("Hali hech kim odam qo‘shmagan.")
        return
    # Top 100
    items = sorted(FOYDALANUVCHI_HISOBI.items(), key=lambda x: x[1], reverse=True)[:100]
    lines = ["🏆 <b>Eng ko‘p odam qo‘shganlar</b> (TOP 100):"]
    for i, (uid, cnt) in enumerate(items, start=1):
        lines.append(f"{i}. <code>{uid}</code> — {cnt} ta")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

# --------- /cleangroup ---------
async def cleangroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("⛔ Bu komanda faqat adminlar uchun.")
        return
    FOYDALANUVCHI_HISOBI.clear()
    await update.message.reply_text("🗑 Barcha foydalanuvchilar hisobi 0 qilindi.")

# --------- /count ---------
async def count_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    cnt = FOYDALANUVCHI_HISOBI.get(uid, 0)
    if MAJBUR_LIMIT > 0:
        qoldi = max(MAJBUR_LIMIT - cnt, 0)
        await update.message.reply_text(f"📊 Siz {cnt} ta odam qo‘shgansiz. Qolgan: {qoldi} ta.")
    else:
        await update.message.reply_text(f"📊 Siz {cnt} ta odam qo‘shgansiz. (Majburiy qo‘shish faol emas)")

# --------- /replycount ---------
async def replycount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("⛔ Bu komanda faqat adminlar uchun.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("Iltimos, kimning hisobini ko‘rmoqchi bo‘lsangiz o‘sha xabarga reply qiling.")
        return
    uid = update.message.reply_to_message.from_user.id
    cnt = FOYDALANUVCHI_HISOBI.get(uid, 0)
    await update.message.reply_text(f"👤 <code>{uid}</code> {cnt} ta odam qo‘shgan.", parse_mode="HTML")

# --------- /cleanuser ---------
async def cleanuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("⛔ Bu komanda faqat adminlar uchun.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("Iltimos, kimni 0 qilmoqchi bo‘lsangiz o‘sha foydalanuvchi xabariga reply qiling.")
        return
    uid = update.message.reply_to_message.from_user.id
    FOYDALANUVCHI_HISOBI[uid] = 0
    await update.message.reply_text(f"🗑 <code>{uid}</code> foydalanuvchi hisobi 0 qilindi.", parse_mode="HTML")

# --------- Yangi a'zolarni hisoblash ---------
async def on_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    adder = msg.from_user  # qo'shgan shaxs
    members = msg.new_chat_members or []
    if not adder:
        return
    for m in members:
        if adder.id != m.id:
            FOYDALANUVCHI_HISOBI[adder.id] += 1
    try:
        await msg.delete()
    except:
        pass

# --------- Majburiy limitni nazorat qilish (oddiy user xabarlari) ---------
async def majbur_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if MAJBUR_LIMIT <= 0:
        return
    msg = update.message
    if not msg:
        return
    if await is_privileged_message(msg, context.bot):
        return
    uid = msg.from_user.id
    cnt = FOYDALANUVCHI_HISOBI.get(uid, 0)
    if cnt >= MAJBUR_LIMIT:
        return
    try:
        await msg.delete()
    except:
        return
    qoldi = max(MAJBUR_LIMIT - cnt, 0)
    kb = [[InlineKeyboardButton("✅ Odam qo‘shdim", callback_data="check_added")]]
    await context.bot.send_message(
        chat_id=msg.chat_id,
        text=f"⚠️ Guruhda yozish uchun {MAJBUR_LIMIT} ta odam qo‘shishingiz kerak! Qolgan: {qoldi} ta.",
        reply_markup=InlineKeyboardMarkup(kb)
    )

# --------- Callback: check_added ---------
async def on_check_added(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    cnt = FOYDALANUVCHI_HISOBI.get(uid, 0)
    if cnt >= MAJBUR_LIMIT:
        await q.edit_message_text("✅ Talab bajarilgan! Endi guruhda yozishingiz mumkin.")
    else:
        qoldi = max(MAJBUR_LIMIT - cnt, 0)
        await q.edit_message_text(f"❌ Hali yetarli emas. Qolgan: {qoldi} ta.")

# --------- Bot komandalarini o'rnatish ---------
async def set_commands(app):
    await app.bot.set_my_commands(commands=[
        BotCommand("help", "Bot qo'llanmasi"),
        BotCommand("majbur", "Majburiy odam qo‘shish limitini o‘rnatish"),
        BotCommand("majburoff", "Majburiy qo‘shishni o‘chirish"),
        BotCommand("top", "TOP 100 ro‘yxati"),
        BotCommand("cleangroup", "Hamma hisobini 0 qilish"),
        BotCommand("count", "Siz nechta qo‘shgansiz"),
        BotCommand("replycount", "Reply qilinganni hisobini ko‘rish"),
        BotCommand("cleanuser", "Reply qilinganni hisobini 0 qilish"),
    ], scope=BotCommandScopeAllPrivateChats())

# --------- App ---------
app = ApplicationBuilder().token(TOKEN).build()

# Handlers
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_cmd))
app.add_handler(CommandHandler("majbur", majbur))
app.add_handler(CallbackQueryHandler(on_set_limit, pattern="^set_limit:"))
app.add_handler(CommandHandler("majburoff", majburoff))
app.add_handler(CommandHandler("top", top_cmd))
app.add_handler(CommandHandler("cleangroup", cleangroup))
app.add_handler(CommandHandler("count", count_cmd))
app.add_handler(CommandHandler("replycount", replycount))
app.add_handler(CommandHandler("cleanuser", cleanuser))

# New/left members (kirish/chiqish) — kirishda adder hisoblanaadi
app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_new_members))

# Majburiy limit filter — barcha non-command xabarlar
media_filters = (
    filters.TEXT |
    filters.PHOTO |
    filters.VIDEO |
    filters.Document.ALL |
    filters.ANIMATION |
    filters.VOICE |
    filters.VIDEO_NOTE |
    filters.Sticker.ALL
)
app.add_handler(MessageHandler(media_filters & (~filters.COMMAND), majbur_filter))

# --------- Run ---------
async def main():
    await set_commands(app)
    logging.info("✅ Majbur bot ishga tushdi...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    start_web()
    asyncio.get_event_loop().run_until_complete(main())
