
import threading
import os
import re
import logging
from collections import defaultdict

from flask import Flask

from telegram import (
    Update, BotCommand, BotCommandScopeAllPrivateChats, ChatPermissions,
    InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

# ---------------------- Flask healthcheck ----------------------
app_flask = Flask(__name__)

@app_flask.route("/")
def home():
    return "Bot ishlayapti!"

def run_web():
    app_flask.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))

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
FOYDALANUVCHI_HISOBI = defaultdict(int)  # user_id -> count
RUXSAT_USER_IDS = set()

# ------------------ Helperlar ------------------
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
    # creator/administrator/anonymous admin
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

async def kanal_tekshir(user_id: int, bot) -> bool:
    global KANAL_USERNAME
    if not KANAL_USERNAME:
        return True
    try:
        member = await bot.get_chat_member(KANAL_USERNAME, user_id)
        return member.status in ("member", "creator", "administrator")
    except Exception as e:
        log.warning(f"kanal_tekshir xatolik: {e}")
        return False

def matndan_sozlar_olish(matn: str):
    return re.findall(r"\b\w+\b", (matn or "").lower())

UYATLI_SOZLAR = {
    "am","qotaq","kot","tashak","fuck","bitch","pidor","gandon",
    "qo'taq","ko't","sik","sikish","mudak","nahuy","naxxuy","pohuy"
}

# ------------------ Commands ------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    FOYDALANUVCHILAR.add(update.effective_user.id)
    kb = [[InlineKeyboardButton("➕ Guruhga qo‘shish",
                                url=f"https://t.me/{context.bot.username}?startgroup=start")]]
    await update.effective_message.reply_text(
        "<b>Salom👋</b>\n"
        "Men reklamalarni, ssilkalarni va kirdi-chiqdi xabarlarni guruhdan o‘chiraman, "
        "majburiy kanalga a'zo bo‘ldiraman, 18+ so‘zlarni tozalayman va foydali komandalar bilan yordam beraman.\n\n"
        "Bot komandalari qo‘llanmasi 👉 /help\n\n"
        "<b>Admin</b> huquqi berishni unutmang 🙂",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📌 <b>Buyruqlar ro‘yxati</b>\n\n"
        "🔹 <b>/id</b> - Акканунтингиз ID сини аниқлайди.\n"
        "🔹 <b>/tun</b> - Барча ёзилган хабарлар автоматик ўчирилади.\n"
        "🔹 <b>/tunoff</b> - Тун режими ўчирилади.\n"
        "🔹 <b>/ruxsat</b> - Reply орқали белгиланган одамга рухсат берилади.\n"
        "🔹 <b>/kanal @username</b> - Каналга азо бўлишга мажбурлайди.\n"
        "🔹 <b>/kanaloff</b> - Каналга мажбур азо бўлишни ўчиради.\n"
        "🔹 <b>/majbur [son]</b> — Majburiy odam qo‘shish limitini o‘rnatish (min 3, max 25). Agar son yozilmasa, menyu chiqadi.\n"
        "🔹 <b>/majburoff</b> — Majburiy qo‘shishni o‘chirish.\n"
        "🔹 <b>/top</b> — Eng ko‘p qo‘shgan TOP 100.\n"
        "🔹 <b>/cleangroup</b> — Hamma hisobini 0 qilish.\n"
        "🔹 <b>/count</b> — Siz nechta odam qo‘shgansiz.\n"
        "🔹 <b>/replycount</b> — Reply qilingan foydalanuvchi hisobi.\n"
        "🔹 <b>/cleanuser</b> — Reply qilingan foydalanuvchi hisоби 0.\n"
    )
    await update.effective_message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)

async def id_berish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    user = update.effective_user
    await update.effective_message.reply_text(f"🆔 {user.first_name}, sizning Telegram ID’ingiz: {user.id}")

async def tun(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global TUN_REJIMI
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Faqat adminlar.")
    TUN_REJIMI = True
    await update.effective_message.reply_text("🌙 Tun rejimi yoqildi. Oddiy foydalanuvchi xabarlari o‘chiriladi.")

async def tunoff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global TUN_REJIMI
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Faqat adminlar.")
    TUN_REJIMI = False
    await update.effective_message.reply_text("🌞 Tun rejimi o‘chirildi.")

async def ruxsat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Faqat adminlar.")
    if not update.effective_message.reply_to_message:
        return await update.effective_message.reply_text("Iltimos, foydalanuvchi xabariga reply qiling.")
    uid = update.effective_message.reply_to_message.from_user.id
    RUXSAT_USER_IDS.add(uid)
    await update.effective_message.reply_text(f"✅ <code>{uid}</code> foydalanuvchiga ruxsat berildi.", parse_mode="HTML")

async def kanal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Faqat adminlar.")
    global KANAL_USERNAME
    if context.args:
        KANAL_USERNAME = context.args[0]
        await update.effective_message.reply_text(f"📢 Majburiy kanal: {KANAL_USERNAME}")
    else:
        await update.effective_message.reply_text("Namuna: /kanal @username")

async def kanaloff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Faqat adminlar.")
    global KANAL_USERNAME
    KANAL_USERNAME = None
    await update.effective_message.reply_text("🚫 Majburiy kanal talabi o‘chirildi.")

# -------- Majbur: limit tanlash klaviaturasi --------
def majbur_klaviatura():
    rows = [[3, 5, 7, 10, 12], [15, 18, 20, 22, 25]]
    keyboard = [[InlineKeyboardButton(str(n), callback_data=f"set_limit:{n}") for n in row] for row in rows]
    keyboard.append([InlineKeyboardButton("❌ BEKOR QILISH ❌", callback_data="set_limit:cancel")])
    return InlineKeyboardMarkup(keyboard)

async def majbur(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Faqat adminlar.")
    global MAJBUR_LIMIT
    if context.args:
        try:
            val = int(context.args[0])
            if not (3 <= val <= 25):
                raise ValueError
            MAJBUR_LIMIT = val
            await update.effective_message.reply_text(
                f"✅ Majburiy odam qo‘shish limiti: <b>{MAJBUR_LIMIT}</b>",
                parse_mode="HTML"
            )
        except ValueError:
            await update.effective_message.reply_text(
                "❌ Noto‘g‘ri qiymat. Ruxsat etilgan oraliq: <b>3–25</b>. Masalan: <code>/majbur 10</code>",
                parse_mode="HTML"
            )
    else:
        await update.effective_message.reply_text(
            "👥 Guruhda majburiy odam qo‘shishni nechta qilib belgilay? 👇\n"
            "Qo‘shish shart emas — /majburoff",
            reply_markup=majbur_klaviatura()
        )

async def on_set_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.callback_query.answer("Faqat adminlar!", show_alert=True)
    q = update.callback_query
    await q.answer()
    data = q.data.split(":", 1)[1]
    global MAJBUR_LIMIT
    if data == "cancel":
        return await q.edit_message_text("❌ Bekor qilindi.")
    try:
        val = int(data)
        if not (3 <= val <= 25):
            raise ValueError
        MAJBUR_LIMIT = val
        await q.edit_message_text(f"✅ Majburiy limit: <b>{MAJBUR_LIMIT}</b>", parse_mode="HTML")
    except Exception:
        await q.edit_message_text("❌ Noto‘g‘ri qiymat.")

async def majburoff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Faqat adminlar.")
    global MAJBUR_LIMIT
    MAJBUR_LIMIT = 0
    await update.effective_message.reply_text("🚫 Majburiy odam qo‘shish o‘chirildi.")

async def top_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Faqat adminlar.")
    if not FOYDALANUVCHI_HISOBI:
        return await update.effective_message.reply_text("Hali hech kim odam qo‘shmagan.")
    items = sorted(FOYDALANUVCHI_HISOBI.items(), key=lambda x: x[1], reverse=True)[:100]
    lines = ["🏆 <b>Eng ko‘p odam qo‘shganlar</b> (TOP 100):"]
    for i, (uid, cnt) in enumerate(items, start=1):
        lines.append(f"{i}. <code>{uid}</code> — {cnt} ta")
    await update.effective_message.reply_text("\n".join(lines), parse_mode="HTML")

async def cleangroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Faqat adminlar.")
    FOYDALANUVCHI_HISOBI.clear()
    RUXSAT_USER_IDS.clear()
    await update.effective_message.reply_text("🗑 Barcha foydalanuvchilar hisobi va imtiyozlar 0 qilindi.")

async def count_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    cnt = FOYDALANUVCHI_HISOBI.get(uid, 0)
    if MAJBUR_LIMIT > 0:
        qoldi = max(MAJBUR_LIMIT - cnt, 0)
        await update.effective_message.reply_text(f"📊 Siz {cnt} ta odam qo‘shgansiz. Qolgan: {qoldi} ta.")
    else:
        await update.effective_message.reply_text(f"📊 Siz {cnt} ta odam qo‘shgansiz. (Majburiy qo‘shish faol emas)")

async def replycount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Faqat adminlar.")
    msg = update.effective_message
    if not msg.reply_to_message:
        return await msg.reply_text("Iltimos, kimning hisobini ko‘rmoqchi bo‘lsangiz o‘sha xabarga reply qiling.")
    uid = msg.reply_to_message.from_user.id
    cnt = FOYDALANUVCHI_HISOBI.get(uid, 0)
    await msg.reply_text(f"👤 <code>{uid}</code> {cnt} ta odam qo‘shgan.", parse_mode="HTML")

async def cleanuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Faqat adminlar.")
    msg = update.effective_message
    if not msg.reply_to_message:
        return await msg.reply_text("Iltimos, kimni 0 qilmoqchi bo‘lsangiz o‘sha foydalanuvchi xabariga reply qiling.")
    uid = msg.reply_to_message.from_user.id
    FOYDALANUVCHI_HISOBI[uid] = 0
    RUXSAT_USER_IDS.discard(uid)
    await msg.reply_text(f"🗑 <code>{uid}</code> foydalanuvchi hisobi 0 qilindi (imtiyoz o‘chirildi).", parse_mode="HTML")

# --------- Callbacks (kanal / majbur) ---------
async def kanal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    if not KANAL_USERNAME:
        return await q.edit_message_text("⚠️ Kanal sozlanmagan.")
    try:
        member = await context.bot.get_chat_member(KANAL_USERNAME, user_id)
        if member.status in ("member", "administrator", "creator"):
            await context.bot.restrict_chat_member(
                chat_id=q.message.chat.id,
                user_id=user_id,
                permissions=ChatPermissions(
                    can_send_messages=True, can_send_media_messages=True, can_send_polls=True,
                    can_send_other_messages=True, can_add_web_page_previews=True, can_invite_users=True
                )
            )
            await q.edit_message_text("✅ A’zo bo‘lganingiz tasdiqlandi. Endi guruhda yozishingiz mumkin.")
        else:
            await q.edit_message_text("❌ Hali kanalga a’zo emassiz.")
    except Exception:
        await q.edit_message_text("⚠️ Tekshirishda xatolik. Kanal username noto‘g‘ri yoki bot kanalga a’zo emas.")

async def on_check_added(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    cnt = FOYDALANUVCHI_HISOBI.get(uid, 0)
    if uid in RUXSAT_USER_IDS or (MAJBUR_LIMIT > 0 and cnt >= MAJBUR_LIMIT):
        await q.edit_message_text("✅ Talab bajarilgan! Endi guruhda yozishingiz mumkin.")
    else:
        qoldi = max(MAJBUR_LIMIT - cnt, 0)
        await q.edit_message_text(f"❌ Hali yetarli emas. Qolgan: {qoldi} ta.")

async def on_grant_priv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    chat = q.message.chat if q.message else None
    user = q.from_user
    if not (chat and user):
        return await q.answer()
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status not in ("administrator", "creator"):
            return await q.answer("Faqat adminlar imtiyoz bera oladi!", show_alert=True)
    except Exception:
        return await q.answer("Tekshirishda xatolik.", show_alert=True)
    await q.answer()
    try:
        target_id = int(q.data.split(":", 1)[1])
    except Exception:
        return await q.edit_message_text("❌ Noto‘g‘ri ma'lumot.")
    RUXSAT_USER_IDS.add(target_id)
    await q.edit_message_text(f"🎟 <code>{target_id}</code> foydalanuvchiga imtiyoz berildi. Endi u yozishi mumkin.", parse_mode="HTML")

# ------------------------------ Filters -----------------------------------
async def reklama_va_soz_filtri(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not msg.chat or not msg.from_user:
        return

    # Admin/whitelist bypass
    if await is_privileged_message(msg, context.bot):
        return
    if msg.from_user.id in WHITELIST or (msg.from_user.username and msg.from_user.username in WHITELIST):
        return

    # Tun rejimi
    if TUN_REJIMI:
        try:
            await msg.delete()
        except:
            pass
        return

    # Kanalga a'zolik
    if not await kanal_tekshir(msg.from_user.id, context.bot):
        try:
            await msg.delete()
        except:
            pass
        kb = [[InlineKeyboardButton("✅ Men a’zo bo‘ldim", callback_data="kanal_azo")]]
        await context.bot.send_message(
            chat_id=msg.chat_id,
            text=f"⚠️ {msg.from_user.first_name}, siz {KANAL_USERNAME} kanalga a’zo emassiz!",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    text = msg.text or msg.caption or ""
    entities = msg.entities or msg.caption_entities or []

    # URL/mention
    for ent in entities:
        if ent.type in ("text_link", "url", "mention"):
            url = getattr(ent, "url", "") or ""
            if url and ("t.me" in url or "telegram.me" in url):
                try:
                    await msg.delete()
                except:
                    pass
                await context.bot.send_message(
                    chat_id=msg.chat_id,
                    text=f"⚠️ {msg.from_user.first_name}, yashirin ssilka yuborish taqiqlangan!"
                )
                return

    if any(x in text for x in ("t.me","telegram.me","@","www.","https://youtu.be","http://","https://")):
        try:
            await msg.delete()
        except:
            pass
        await context.bot.send_message(
            chat_id=msg.chat_id,
            text=f"⚠️ {msg.from_user.first_name}, reklama/ssilka yuborish taqiqlangan!"
        )
        return

    # So'kinish
    sozlar = matndan_sozlar_olish(text)
    if any(s in UYATLI_SOZLAR for s in sozlar):
        try:
            await msg.delete()
        except:
            pass
        await context.bot.send_message(
            chat_id=msg.chat_id,
            text=f"⚠️ {msg.from_user.first_name}, guruhda so‘kinish taqiqlangan!"
        )
        return

async def majbur_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if MAJBUR_LIMIT <= 0:
        return
    msg = update.effective_message
    if not msg or not msg.from_user:
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

# -------------------------- Bot command menus -----------------------------
async def set_commands(app):
    await app.bot.set_my_commands(
        commands=[
            BotCommand("start", "Bot haqida ma'lumot"),
            BotCommand("help", "Bot qo'llanmasi"),
            BotCommand("id", "Sizning ID’ingiz"),
            BotCommand("count", "Siz nechta qo‘shgansiz"),
            BotCommand("top", "TOP 100 ro‘yxati"),
            BotCommand("replycount", "(reply) foydalanuvchi nechta qo‘shganini ko‘rish"),
            BotCommand("majbur", "Majburiy odam limitini (3–25) o‘rnatish"),
            BotCommand("majburoff", "Majburiy qo‘shishni o‘chirish"),
            BotCommand("cleangroup", "Hamma hisobini 0 qilish"),
            BotCommand("cleanuser", "(reply) foydalanuvchi hisobini 0 qilish"),
            BotCommand("ruxsat", "(reply) imtiyoz berish"),
            BotCommand("kanal", "Majburiy kanalni sozlash"),
            BotCommand("kanaloff", "Majburiy kanalni o‘chirish"),
            BotCommand("tun", "Tun rejimini yoqish"),
            BotCommand("tunoff", "Tun rejimini o‘chirish"),
        ],
        scope=BotCommandScopeAllPrivateChats()
    )

# --------------------------------- Main -----------------------------------
def main():
    start_web()
    app = ApplicationBuilder().token(TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help))
    app.add_handler(CommandHandler("id", id_berish))
    app.add_handler(CommandHandler("tun", tun))
    app.add_handler(CommandHandler("tunoff", tunoff))
    app.add_handler(CommandHandler("ruxsat", ruxsat))
    app.add_handler(CommandHandler("kanal", kanal))
    app.add_handler(CommandHandler("kanaloff", kanaloff))
    app.add_handler(CommandHandler("majbur", majbur))
    app.add_handler(CommandHandler("majburoff", majburoff))
    app.add_handler(CommandHandler("top", top_cmd))
    app.add_handler(CommandHandler("cleangroup", cleangroup))
    app.add_handler(CommandHandler("count", count_cmd))
    app.add_handler(CommandHandler("replycount", replycount))
    app.add_handler(CommandHandler("cleanuser", cleanuser))

    # Callbacks
    app.add_handler(CallbackQueryHandler(on_set_limit, pattern=r"^set_limit:"))
    app.add_handler(CallbackQueryHandler(kanal_callback, pattern=r"^kanal_azo$"))
    app.add_handler(CallbackQueryHandler(on_check_added, pattern=r"^check_added$"))
    app.add_handler(CallbackQueryHandler(on_grant_priv, pattern=r"^grant:"))

    # New members
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_new_members))

    # Filters: majbur first (higher priority), then others
    media_filters = (
        filters.TEXT |
        filters.PHOTO |
        filters.VIDEO |
        filters.Document.ALL |
        filters.ANIMATION |
        filters.VOICE |
        filters.VIDEO_NOTE
    )
    app.add_handler(MessageHandler(media_filters & (~filters.COMMAND), majbur_filter), group=-1)
    app.add_handler(MessageHandler(media_filters & (~filters.COMMAND), reklama_va_soz_filtri))

    app.post_init = set_commands
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
