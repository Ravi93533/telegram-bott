
import threading
import os
import re
import logging
import asyncio
from collections import defaultdict

from flask import Flask

from telegram import (
    Update, BotCommand, BotCommandScopeAllPrivateChats, ChatPermissions,
    InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, ChatMemberHandler, filters
)

# ---------------------- Flask healthcheck ----------------------
app_flask = Flask(__name__)

@app_flask.route("/")
def home():
    return "Bot ishlayapti!"

def run_web():
    app_flask.run(host="0.0.0.0", port=8080)

def start_web():
    threading.Thread(target=run_web, daemon=True).start()

# -------------------------- Logging ---------------------------
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)

# ---------------------- Global holat --------------------------
TOKEN = os.getenv("TOKEN") or "YOUR_TOKEN_HERE"

WHITELIST = {165553982, "Yunus1995"}
TUN_REJIMI = False
KANAL_USERNAME = None
FOYDALANUVCHILAR = set()

# Majburiy qo'shish
MAJBUR_LIMIT = 0  # 0 => o'chirilgan
FOYDALANUVCHI_HISOBI = defaultdict(int)
RUXSAT_USER_IDS = set()

# ------------------ Admin aniqlash yordamchi ------------------
async def is_admin(update: Update) -> bool:
    chat = update.effective_chat
    user = update.effective_user
    if not (chat and user):
        return False
    try:
        member = await update.get_bot().get_chat_member(chat.id, user.id)
        return member.status in ("administrator", "creator")
    except Exception as e:
        log.warning(f"is_admin tekshiruvda xatolik: {e}")
        return False

async def is_privileged_message(msg, bot) -> bool:
    """Creator/administrator va anonymous admin (sender_chat == chat.id) yozuvlarini aniqlash."""
    try:
        chat = msg.chat
        user = msg.from_user
        if getattr(msg, "sender_chat", None) and msg.sender_chat.id == chat.id:
            return True
        if user:
            member = await bot.get_chat_member(chat.id, user.id)
            if member.status in ("administrator", "creator"):
                return True
    except Exception as e:
        log.warning(f"is_privileged_message xatolik: {e}")
    return False

# ------------------------- Kanal tekshir ----------------------
async def kanal_tekshir(update: Update, bot) -> bool:
    global KANAL_USERNAME
    if not KANAL_USERNAME:
        return True
    try:
        user = update.effective_user
        member = await bot.get_chat_member(KANAL_USERNAME, user.id)
        return member.status in ["member", "creator", "administrator"]
    except Exception as e:
        log.warning(f"kanal_tekshir xatolik: {e}")
        return False

# ------------------ So'kinish so'zlari ro'yxati ---------------
uyatli_sozlar = {
    "am", "qotaq", "kot", "tashak", "fuck", "bitch", "pidor", "gandon",
    "qo'taq", "ko't", "sik", "sikish", "mudak", "nahuy", "naxxuy", "pohuy",
}

def matndan_sozlar_olish(matn: str):
    return re.findall(r"\b\w+\b", (matn or "").lower())

# ------------------ ASOSIY FILTR HANDLER ----------------------
async def reklama_va_soz_filtri(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        msg = update.message
        if not msg:
            return
        user = msg.from_user
        chat_id = msg.chat_id
        msg_id = msg.message_id

        text = msg.text or msg.caption or ""
        entities = msg.entities or msg.caption_entities or []

        # 0) PRIVILEGED (creator/administrator/anonymous admin) va WHITELIST — BYPASS
        privileged = await is_privileged_message(msg, context.bot)
        whitelisted = (user and (user.id in WHITELIST or (user.username and user.username in WHITELIST)))
        if privileged or whitelisted:
            return

        # 1) FORWARD xabarlar — taqiqlanadi
        if getattr(msg, "forward_from_chat", None) or getattr(msg, "forward_sender_name", None):
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ {user.first_name}, forward qilingan xabar yuborish taqiqlangan!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ Guruhga qo‘shish", url=f"https://t.me/{context.bot.username}?startgroup=start")]])
            )
            return

        # 2) TUN REJIMI
        if TUN_REJIMI:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            return

        # 3) Kanalga a’zolik tekshiruvi (faqat oddiy foydalanuvchiga)
        if not await kanal_tekshir(update, context.bot):
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            keyboard = [[InlineKeyboardButton("✅ Men a’zo bo‘ldim", callback_data="kanal_azo")]]
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ {user.first_name}, siz {KANAL_USERNAME} kanalga a’zo emassiz!",
                reply_markup=InlineKeyboardMarkup(keyboard))
            return

        # 4) Yashirin ssilkalar va textdagi ssilkalar
        for ent in entities:
            if ent.type in ["text_link", "url", "mention"]:
                url = getattr(ent, "url", "") or ""
                if url and ("t.me" in url or "telegram.me" in url):
                    await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"⚠️ {user.first_name}, yashirin ssilka yuborish taqiqlangan!",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ Guruhga qo‘shish", url=f"https://t.me/{context.bot.username}?startgroup=start")]])
                    )
                    return

        if any(x in text for x in ["t.me", "telegram.me", "@", "www.", "https://youtu.be", "http://", "https://"]):
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ {user.first_name}, reklama yuborish taqiqlangan!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ Guruhga qo‘shish", url=f"https://t.me/{context.bot.username}?startgroup=start")]])
            )
            return

        # 5) So‘kinish
        sozlar = matndan_sozlar_olish(text)
        if any(soz in uyatli_sozlar for soz in sozlar):
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ {user.first_name}, guruhda so‘kinish taqiqlangan!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ Guruhga qo‘shish", url=f"https://t.me/{context.bot.username}?startgroup=start")]])
            )
            return

    except Exception as e:
        logging.error(f"[Xatolik] Filtrda: {e}")

# ------------------ Majbur blok ------------------
def majbur_klaviatura():
    rows = [[3, 5, 7, 10, 12], [15, 18, 20, 22, 25]]
    keyboard = [[InlineKeyboardButton(str(n), callback_data=f"set_limit:{n}") for n in row] for row in rows]
    keyboard.append([InlineKeyboardButton("❌ BEKOR QILISH ❌", callback_data="set_limit:cancel")])
    return InlineKeyboardMarkup(keyboard)

async def majbur(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("⛔ Bu komanda faqat adminlar uchun.")
        return
    global MAJBUR_LIMIT
    if context.args:
        try:
            val = int(context.args[0])
            if not (3 <= val <= 25):
                raise ValueError
            MAJBUR_LIMIT = val
            await update.message.reply_text(f"✅ Majburiy odam qo‘shish limiti: <b>{MAJBUR_LIMIT}</b>", parse_mode="HTML")
        except ValueError:
            await update.message.reply_text("❌ Noto‘g‘ri qiymat. Ruxsat etilgan oraliq: <b>3–25</b>. Masalan: <code>/majbur 10</code>", parse_mode="HTML")
    else:
        await update.message.reply_text(
            "👥 Guruhda majburiy odam qo‘shishni nechta qilib belgilay? 👇\nQo‘shish shart emas — /majburoff",
            reply_markup=majbur_klaviatura()
        )

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
        if not (3 <= val <= 25):
            raise ValueError
        MAJBUR_LIMIT = val
        await query.edit_message_text(f"✅ Majburiy odam qo‘shish limiti: <b>{MAJBUR_LIMIT}</b>", parse_mode="HTML")
    except Exception:
        await query.edit_message_text("❌ Noto‘g‘ri qiymat.")

async def majburoff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("⛔ Bu komanda faqat adminlar uchun.")
        return
    global MAJBUR_LIMIT
    MAJBUR_LIMIT = 0
    await update.message.reply_text("🚫 Majburiy odam qo‘shish o‘chirildi.")

async def top_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("⛔ Bu komanda faqat adminlar uchun.")
        return
    if not FOYDALANUVCHI_HISOBI:
        await update.message.reply_text("Hali hech kim odam qo‘shmagan.")
        return
    items = sorted(FOYDALANUVCHI_HISOBI.items(), key=lambda x: x[1], reverse=True)[:100]
    lines = ["🏆 <b>Eng ko‘p odam qo‘shganlar</b> (TOP 100):"]
    for i, (uid, cnt) in enumerate(items, start=1):
        lines.append(f"{i}. <code>{uid}</code> — {cnt} ta")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cleangroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("⛔ Bu komanda faqat adminlar uchun.")
        return
    FOYDALANUVCHI_HISOBI.clear()
    RUXSAT_USER_IDS.clear()
    await update.message.reply_text("🗑 Barcha foydalanuvchilar hisobi va imtiyozlar 0 qilindi.")

async def count_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    cnt = FOYDALANUVCHI_HISOBI.get(uid, 0)
    if MAJBUR_LIMIT > 0:
        qoldi = max(MAJBUR_LIMIT - cnt, 0)
        await update.message.reply_text(f"📊 Siz {cnt} ta odam qo‘shgansiz. Qolgan: {qoldi} ta.")
    else:
        await update.message.reply_text(f"📊 Siz {cnt} ta odam qo‘shgansiz. (Majburiy qo‘shish faol emas)")

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

async def cleanuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("⛔ Bu komanda faqat adminlar uchun.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("Iltimos, kimni 0 qilmoqchi bo‘lsangiz o‘sha foydalanuvchi xabariga reply qiling.")
        return
    uid = update.message.reply_to_message.from_user.id
    FOYDALANUVCHI_HISOBI[uid] = 0
    RUXSAT_USER_IDS.discard(uid)
    await update.message.reply_text(f"🗑 <code>{uid}</code> foydalanuvchi hisobi 0 qilindi (imtiyoz o‘chirildi).", parse_mode="HTML")

async def majbur_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if MAJBUR_LIMIT <= 0:
        return
    msg = update.message
    if not msg:
        return
    if await is_privileged_message(msg, context.bot):
        return
    uid = msg.from_user.id
    if uid in RUXSAT_USER_IDS:
        return
    cnt = FOYDALANUVCHI_HISOBI.get(uid, 0)
    if cnt >= MAJBUR_LIMIT:
        return
    try:
        await msg.delete()
    except:
        return
    qoldi = max(MAJBUR_LIMIT - cnt, 0)
    kb = [
        [InlineKeyboardButton("✅ Odam qo‘shdim", callback_data="check_added")],
        [InlineKeyboardButton("🎟 Imtiyoz berish", callback_data=f"grant:{uid}")]
    ]
    await context.bot.send_message(
        chat_id=msg.chat_id,
        text=f"⚠️ Guruhda yozish uchun {MAJBUR_LIMIT} ta odam qo‘shishingiz kerak! Qolgan: {qoldi} ta.",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def on_check_added(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    cnt = FOYDALANUVCHI_HISOBI.get(uid, 0)
    if uid in RUXSAT_USER_IDS or cnt >= MAJBUR_LIMIT:
        await q.edit_message_text("✅ Talab bajarilgan! Endi guruhda yozishingiz mumkin.")
    else:
        qoldi = max(MAJBUR_LIMIT - cnt, 0)
        await q.edit_message_text(f"❌ Hali yetarli emas. Qolgan: {qoldi} ta.")

async def on_grant_priv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    chat = q.message.chat if q.message else None
    user = q.from_user
    if not (chat and user):
        await q.answer()
        return
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status not in ("administrator", "creator"):
            await q.answer("Faqat adminlar imtiyoz bera oladi!", show_alert=True)
            return
    except Exception:
        await q.answer("Tekshirishda xatolik.", show_alert=True)
        return
    await q.answer()
    try:
        target_id = int(q.data.split(":", 1)[1])
    except Exception:
        await q.edit_message_text("❌ Noto‘g‘ri ma'lumot.")
        return
    RUXSAT_USER_IDS.add(target_id)
    await q.edit_message_text(f"🎟 <code>{target_id}</code> foydalanuvchiga imtiyoz berildi. Endi u yozishi mumkin.", parse_mode="HTML")

# ------------------ QOLGAN KOMANDALAR ------------------
async def welcome_goodbye(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        try:
            await update.message.delete()
        except:
            pass

async def id_berish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return
    user = update.message.from_user
    await update.message.reply_text(
        f"🆔 {user.first_name}, sizning Telegram ID’ingiz: {user.id}",
        parse_mode="Markdown")

async def kanal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("⛔ Bu komanda faqat adminlar uchun.")
        return
    global KANAL_USERNAME
    if context.args:
        KANAL_USERNAME = context.args[0]
        await update.message.reply_text(
            f"📢 Kanalga a’zo bo‘lish majburiy: {KANAL_USERNAME}")

async def kanaloff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("⛔ Bu komanda faqat adminlar uchun.")
        return
    global KANAL_USERNAME
    KANAL_USERNAME = None
    await update.message.reply_text("🚫 Kanalga a’zo bo‘lish talabi o‘chirildi.")

async def ruxsat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("⛔ Bu komanda faqat adminlar uchun.")
        return
    if update.message.reply_to_message is not None:
        user_id = update.message.reply_to_message.from_user.id
        RUXSAT_USER_IDS.add(user_id)  # FIX: haqiqiy ruxsat
        await update.message.reply_text("✅ Ruxsat berildi.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    FOYDALANUVCHILAR.add(update.effective_user.id)
    keyboard = [[
        InlineKeyboardButton("➕ Guruhga qo‘shish",
                             url=f"https://t.me/{context.bot.username}?startgroup=start")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "<b>Salom👋</b>\n"
        "Men reklamalarni, ssilkalani va kirdi chiqdi xabarlarni guruhlardan <b>o‘chirib</b> <b>beraman</b>, profilingiz <b>ID</b> gizni aniqlab beraman, majburiy kanalga a'zo bo‘ldiraman, 18+ uyatli so'zlarni o'chiraman va boshqa ko‘plab yordamlar beraman 👨🏻‍✈\n\n"
        "Bot komandalari <b>qo'llanmasi</b> 👉 /help\n\n"
        "Faqat Ishlashim uchun guruhingizga qo‘shib, <b>ADMIN</b> <b>berishingiz</b> <b>kerak</b> 🙂\n\n"
        "Murojaat uchun👉 @Devona0107",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return
    await update.message.reply_text(f"📊 Botdan foydalangan foydalanuvchilar soni: {len(FOYDALANUVCHILAR)} ta")

async def kanal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    await query.answer()
    if not KANAL_USERNAME:
        await query.edit_message_text("⚠️ Kanal sozlanmagan.")
        return
    try:
        member = await context.bot.get_chat_member(KANAL_USERNAME, user.id)
        if member.status in ["member", "administrator", "creator"]:
            await context.bot.restrict_chat_member(
                chat_id=query.message.chat.id,
                user_id=user.id,
                permissions=ChatPermissions(can_send_messages=True,
                                            can_send_media_messages=True,
                                            can_send_polls=True,
                                            can_send_other_messages=True,
                                            can_add_web_page_previews=True,
                                            can_invite_users=True))
            await query.edit_message_text("✅ A’zo bo‘lganingiz tasdiqlandi. Endi guruhda yozishingiz mumkin.")
        else:
            await query.edit_message_text("❌ Hali kanalga a’zo emassiz.")
    except Exception:
        await query.edit_message_text("⚠️ Tekshirishda xatolik. Kanal username noto‘g‘ri bo‘lishi yoki bot kanalga a’zo bo‘lmasligi mumkin.")

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📌 <b>Buyruqlar ro‘yxati</b>\n\n"
        "🔹 <b>/id</b> - Акканунтингиз ID сини аниқлайди.\n"
        "🔹 <b>/tun</b> - Барча ёзилган хабарлар автоматик ўчирилади.\n"
        "🔹 <b>/tunoff</b> - Тун режими ўчирилади.\n"
        "🔹 <b>/ruxsat</b> - Ответ ёки @ орқали белгиланган одамга рухсат берилади.\n"
        "🔹 <b>/kanal @username</b> - Каналга азо бўлишга мажбурлайди.\n"
        "🔹 <b>/kanaloff</b> - Каналга мажбур азо бўлишни ўчиради.\n"
        "🔹 <b>/majbur [son]</b> — Majburiy odam qo‘shish limitini o‘rnatish (min 3, max 25). Agar son yozilmasa, menyu chiqadi.\n"
        "🔹 <b>/majburoff</b> — Majburiy qo‘shishni o‘chirish.\n"
        "🔹 <b>/top</b> — Eng ko‘p qo‘shgan TOP 100.\n"
        "🔹 <b>/cleangroup</b> — Hamma hisobini 0 qilish.\n"
        "🔹 <b>/count</b> — Siz nechta odam qo‘shgansiz.\n"
        "🔹 <b>/replycount</b> — Reply qilingan foydalanuvchi hisobi.\n"
        "🔹 <b>/cleanuser</b> — Reply qilingan foydalanuvchi hisobi 0.\n"
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def tun(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global TUN_REJIMI
    if not await is_admin(update):
        await update.message.reply_text("⛔ Bu komanda faqat adminlar uchun.")
        return
    TUN_REJIMI = True
    await update.message.reply_text("🌙 Tun rejimi yoqildi. Endi barcha xabarlar o‘chiriladi (admin/creator bundan mustasno).")


async def tunoff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global TUN_REJIMI
    if not await is_admin(update):
        await update.message.reply_text("⛔ Bu komanda faqat adminlar uchun.")
        return
    TUN_REJIMI = False
    await update.message.reply_text("🌤 Tun rejimi o‘chirildi.")


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
async def set_commands(app):
    await app.bot.set_my_commands(commands=[
        BotCommand("help", "Bot qo'llanmasi"),
        BotCommand("id", "Sizning ID’ingizni ko‘rsatadi"),
        BotCommand("tun", "Tun rejimini yoqish"),
        BotCommand("tunoff", "Tun rejimini o‘chirish"),
        BotCommand("kanal", "Majburiy kanalga a'zo bo'lish"),
        BotCommand("kanaloff", "Majburiy kanalga a'zo bo'lishni o'chirish"),
        BotCommand("ruxsat", "Odamga barcha ruxsatlar berish"),
        BotCommand("majbur", "Majburiy odam qo‘shish limitini o‘rnatish (3–25)"),
        BotCommand("majburoff", "Majburiy qo‘shishni o‘chirish"),
        BotCommand("top", "TOP 100 ro‘yxati"),
        BotCommand("cleangroup", "Hamma hisobini 0 qilish"),
        BotCommand("count", "Siz nechta qo‘shgansiz"),
        BotCommand("replycount", "Reply qilinganni hisobini ko‘rish"),
        BotCommand("cleanuser", "Reply qilinganni hisobini 0 qilish"),
    ], scope=BotCommandScopeAllPrivateChats())

# --------------------------- App va handlers ------------------------------
def main():
    start_web()

    app = ApplicationBuilder().token(TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("users", users))
    app.add_handler(CommandHandler("help", help))
    app.add_handler(CommandHandler("id", id_berish))
    app.add_handler(CommandHandler("kanal", kanal))
    app.add_handler(CommandHandler("kanaloff", kanaloff))
    app.add_handler(CommandHandler("ruxsat", ruxsat))
    app.add_handler(CommandHandler("tun", tun))
    app.add_handler(CommandHandler("tunoff", tunoff))

    app.add_handler(CommandHandler("majbur", majbur))
    app.add_handler(CallbackQueryHandler(on_set_limit, pattern=r"^set_limit:"))
    app.add_handler(CommandHandler("majburoff", majburoff))
    app.add_handler(CommandHandler("top", top_cmd))
    app.add_handler(CommandHandler("cleangroup", cleangroup))
    app.add_handler(CommandHandler("count", count_cmd))
    app.add_handler(CommandHandler("replycount", replycount))
    app.add_handler(CommandHandler("cleanuser", cleanuser))

    # Callbacks
    app.add_handler(CallbackQueryHandler(kanal_callback, pattern=r"^kanal_azo$"))
    app.add_handler(CallbackQueryHandler(on_check_added, pattern=r"^check_added$"))
    app.add_handler(CallbackQueryHandler(on_grant_priv, pattern=r"^grant:"))

    # New member messages
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_goodbye))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_new_members))
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, welcome_goodbye))

    # Filters
    media_filters = (
        filters.TEXT |
        filters.PHOTO |
        filters.VIDEO |
        filters.Document.ALL |
        filters.ANIMATION |
        filters.VOICE |
        filters.VIDEO_NOTE
    )
    app.add_handler(MessageHandler(media_filters & (~filters.COMMAND), reklama_va_soz_filtri))
    app.add_handler(MessageHandler(media_filters & (~filters.COMMAND), majbur_filter))

    app.post_init = set_commands
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
