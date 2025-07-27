
import threading
from flask import Flask

app_flask = Flask(__name__)

@app_flask.route("/")
def home():
    return "Bot ishlayapti!"

@app_flask.route("/webhook", methods=["POST"])
def webhook():
    return "OK", 200
    return "Bot ishlayapti!"

def run_web():
    app_flask.run(host="0.0.0.0", port=8080)

def start_web():
    threading.Thread(target=run_web).start()

from telegram import Update, BotCommand, BotCommandScopeAllPrivateChats
from telegram.ext import (CallbackQueryHandler, ApplicationBuilder,
                          CommandHandler, MessageHandler, filters,
                          ContextTypes, ChatMemberHandler)
import re
import os
import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions

# 🔒 Foydalanuvchi adminmi, tekshirish
async def is_admin(update: Update) -> bool:
    chat = update.effective_chat
    user = update.effective_user
    member = await chat.get_member(user.id)
    return member.status in ("administrator", "creator")

TOKEN = os.getenv("TOKEN") or "YOUR_TOKEN_HERE"

WHITELIST = [165553982, "Yunus1995"]
MAJBUR_LIMIT = 10
RUXSAT_USER_IDS = set()
MAJBUR_USERS = {}
TUN_REJIMI = False
KANAL_USERNAME = None
FOYDALANUVCHI_HISOBI = {}
BLOK_VAQTLARI = {}  # Foydalanuvchi ID -> blok tugash vaqti
BLOK_MUDDATI = 300  # 5 daqiqa sekundlarda

async def kanal_tekshir(update: Update):
    global KANAL_USERNAME
    if not KANAL_USERNAME:
        return True
    try:
        user = update.message.from_user
        member = await update.get_bot().get_chat_member(KANAL_USERNAME, user.id)
        return member.status in ["member", "creator", "administrator"]
    except:
        return False

# ✅ Reklama va majburiy qo‘shish tekshiruvi
async def reklama_aniqlash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global TUN_REJIMI
    user = update.message.from_user
    text = update.message.text
    chat_id = update.message.chat_id
    msg_id = update.message.message_id

    if user.id in WHITELIST or (user.username and user.username in WHITELIST):
        return

    if TUN_REJIMI:
        await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        return

    if not await kanal_tekshir(update):
        await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        keyboard = [[
            InlineKeyboardButton("✅ Men a’zo bo‘ldim", callback_data="kanal_azo")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"⚠️ {user.first_name}, siz {KANAL_USERNAME} kanalga a’zo emassiz!",
            reply_markup=reply_markup)
        return

    isadmin = await is_admin(update)
    odamlar_soni = MAJBUR_USERS.get(user.id, 0)
    hozir = int(time.time())
    blok_vaqti = BLOK_VAQTLARI.get(user.id, 0)

    if not isadmin and MAJBUR_LIMIT > 0 and odamlar_soni < MAJBUR_LIMIT and user.id not in RUXSAT_USER_IDS:
        if hozir < blok_vaqti:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            return

        BLOK_VAQTLARI[user.id] = hozir + BLOK_MUDDATI
        await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        keyboard = [[InlineKeyboardButton("✅ Odam qo‘shdim", callback_data="odam_qoshdim")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"⚠️ Guruhda yozish uchun {MAJBUR_LIMIT} ta odam qo‘shishingiz kerak! Siz 5 daqiqa davomida yozishni cheklangansiz.",
            reply_markup=reply_markup
        )
        return

    if re.search(r"(http|www\.|t\.me/|@|reklama|reklam)", text, re.IGNORECASE):
        await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"⚠️ {user.first_name}, guruhda reklama taqiqlangan.")
# ✅ Guruhga kirgan yoki chiqqan foydalanuvchilar xabarini o‘chirish
async def welcome_goodbye(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.delete()


# ✅ /id faqat private chatda
async def id_berish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return
    user = update.message.from_user
    await update.message.reply_text(
        f"🆔 {user.first_name}, sizning Telegram ID’ingiz: {user.id}",
        parse_mode="Markdown")


# 🧩 Interaktiv majburiy odam qo‘shish menyusi


async def majbur(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("⛔ Bu komanda faqat adminlar uchun.")
        return
    global MAJBUR_USERS
    MAJBUR_USERS.clear()
    keyboard = [[
        InlineKeyboardButton(str(i), callback_data=f"majbur_{i}")
        for i in range(5, 30, 5)
    ],
                [
                    InlineKeyboardButton(str(i), callback_data=f"majbur_{i}")
                    for i in range(30, 55, 5)
                ],
                [
                    InlineKeyboardButton(str(i), callback_data=f"majbur_{i}")
                    for i in range(60, 110, 10)
                ],
                [
                    InlineKeyboardButton("❌ BEKOR QILISH ❌",
                                         callback_data="majbur_cancel")
                ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👥 Guruhda majburiy odam qo‘shishni nechta qilib belgilay? 👇 Qo‘shish shart emas - /majburoff",
        reply_markup=reply_markup)




async def majbur_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAJBUR_LIMIT
    query = update.callback_query
    user = query.from_user
    await query.answer()
    if not await is_admin(update):
        await query.edit_message_text("⛔ Bu amal faqat adminlar uchun.")
        return
    data = query.data
    if data == "majbur_cancel":
        await query.edit_message_text("❌ Bekor qilindi.")
    elif data.startswith("majbur_"):
        try:
            son = int(data.split("_")[1])
            MAJBUR_LIMIT = son
            await query.edit_message_text(
                f"🔒 Endi har bir foydalanuvchi {MAJBUR_LIMIT} ta odam qo‘shishi shart."
            )
        except:
            await query.edit_message_text("⚠️ Noto‘g‘ri son.")


async def majbur_tekshir_callback(update: Update,
                                  context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    await query.answer()

    if query.data == "odam_qoshdim":
        user_id = user.id
        odam_soni = FOYDALANUVCHI_HISOBI.get(user_id, 0)

        if odam_soni >= MAJBUR_LIMIT or user_id in RUXSAT_USER_IDS:
            if user_id in MAJBUR_USERS:
                del MAJBUR_USERS[user_id]
            await context.bot.restrict_chat_member(
                chat_id=query.message.chat.id,
                user_id=user_id,
                permissions=ChatPermissions(
                    can_send_messages=True,
                    can_send_media_messages=True,
                    can_send_polls=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True,
                    can_invite_users=True
                )
            )
            await query.edit_message_text("✅ Siz endi guruhda yozishingiz mumkin.")
        else:
            qolgan = MAJBUR_LIMIT - odam_soni
            await query.edit_message_text(
                f"❌ Hali yetarli odam qo‘shmagansiz. Yana {qolgan} ta odam qo‘shing.")



async def majburoff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("⛔ Bu komanda faqat adminlar uchun.")
        return
    global MAJBUR_USERS, MAJBUR_LIMIT
    MAJBUR_LIMIT = 0
    for user_id in list(MAJBUR_USERS.keys()):
        try:
            await context.bot.restrict_chat_member(
                chat_id=update.effective_chat.id,
                user_id=user_id,
                permissions=ChatPermissions(
                    can_send_messages=True,
                    can_send_media_messages=True,
                    can_send_polls=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True,
                    can_invite_users=True
                )
            )
        except:
            continue
    MAJBUR_USERS.clear()
    await update.message.reply_text("✅ Majburiy odam qo‘shish funksiyasi o‘chirildi va barcha foydalanuvchilar yozishdan chiqarildi.")


async def kanal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("⛔ Bu komanda faqat adminlar uchun.")
        return
    global KANAL_USERNAME
    if context.args:
        KANAL_USERNAME = context.args[0]
        await update.message.reply_text(
            f"📢 Kanalga a’zo bo‘lish majburiy: {KANAL_USERNAME}")


# ✅ /kanaloff
async def kanaloff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("⛔ Bu komanda faqat adminlar uchun.")
        return
    global KANAL_USERNAME
    KANAL_USERNAME = None
    await update.message.reply_text("🚫 Kanalga a’zo bo‘lish talabi o‘chirildi."
                                    )


# ✅ /ruxsat
async def ruxsat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("⛔ Bu komanda faqat adminlar uchun.")
        return
    if update.message.reply_to_message:
        user_id = update.message.reply_to_message.from_user.id
        RUXSAT_USER_IDS.add(user_id)
        await update.message.reply_text("✅ Ruxsat berildi.")


# ✅ /top
async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("⛔ Bu komanda faqat adminlar uchun.")
        return
    if not FOYDALANUVCHI_HISOBI:
        await update.message.reply_text("⛔ Hali hech kim odam qo‘shmagan.")
        return
    sorted_users = sorted(FOYDALANUVCHI_HISOBI.items(),
                          key=lambda x: x[1],
                          reverse=True)[:10]
    msg = "🏆 TOP 10 odam qo‘shganlar:\n"
    for uid, count in sorted_users:
        msg += f"{uid}: {count} ta odam qo‘shgan.\n"
    await update.message.reply_text(msg)


# ✅ /count
async def count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    count = FOYDALANUVCHI_HISOBI.get(user_id, 0)
    await update.message.reply_text(f"📈 Siz {count} ta odam qo‘shgansiz.")


# ✅ /replycount
async def replycount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.reply_to_message:
        uid = update.message.reply_to_message.from_user.id
        count = FOYDALANUVCHI_HISOBI.get(uid, 0)
        await update.message.reply_text(
            f"📈 U foydalanuvchi {count} ta odam qo‘shgan.")


# ✅ /cleangroup
async def cleangroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("⛔ Bu komanda faqat adminlar uchun.")
        return
    FOYDALANUVCHI_HISOBI.clear()
    await update.message.reply_text("🧹 Barcha hisoblar tozalandi.")


# ✅ /cleanuser
async def cleanuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("⛔ Bu komanda faqat adminlar uchun.")
        return
    if update.message.reply_to_message:
        uid = update.message.reply_to_message.from_user.id
        FOYDALANUVCHI_HISOBI[uid] = 0
        await update.message.reply_text("🧽 Foydalanuvchi hisob tozalandi.")


# ✅ /tun
async def tun(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("⛔ Bu komanda faqat adminlar uchun.")
        return
    global TUN_REJIMI
    TUN_REJIMI = True
    await update.message.reply_text(
        "🌙 Tun rejimi yoqildi. Endi barcha xabarlar o‘chiriladi.")


# ✅ /tunoff
async def tunoff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("⛔ Bu komanda faqat adminlar uchun.")
        return
    global TUN_REJIMI
    TUN_REJIMI = False
    await update.message.reply_text("🌤 Tun rejimi o‘chirildi.")


# ✅ Guruhga qo‘shilganlar hisobini yuritish
async def on_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.chat_member.new_chat_member.status == "member":
        user_id = update.chat_member.from_user.id
        invited_id = update.chat_member.new_chat_member.user.id
        if user_id != invited_id:
            FOYDALANUVCHI_HISOBI[user_id] = FOYDALANUVCHI_HISOBI.get(
                user_id, 0) + 1
            MAJBUR_USERS[user_id] = MAJBUR_USERS.get(user_id, 0) + 1


# 🟢 Botni ishga tushirish


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
            # ✅ Foydalanuvchiga yozish huquqini tiklash
            await context.bot.restrict_chat_member(
                chat_id=query.message.chat.id,
                user_id=user.id,
                permissions=ChatPermissions(can_send_messages=True,
                                            can_send_media_messages=True,
                                            can_send_polls=True,
                                            can_send_other_messages=True,
                                            can_add_web_page_previews=True,
                                            can_invite_users=True))
            await query.edit_message_text(
                "✅ A’zo bo‘lganingiz tasdiqlandi. Endi guruhda yozishingiz mumkin."
            )
        else:
            await query.edit_message_text("❌ Hali kanalga a’zo emassiz.")
    except:
        await query.edit_message_text(
            "⚠️ Tekshirishda xatolik. Kanal username noto‘g‘ri bo‘lishi yoki bot kanalga a’zo bo‘lmasligi mumkin."
        )


# ✅ /help komandasi
async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📌 <b>Buyruqlar ro‘yxati</b>\n\n"
        "🔹 <b>/id</b> - Акканунтингиз ID сини аниқлайди.\n"
        "🔹 <b>/tun</b> - Барча ёзилган хабарлар автоматик ўчирилади.\n"
        "🔹 <b>/tunoff</b> - Тун режими ўчирилади.\n"
        "🔹 <b>/majbur</b> - Гуруҳга 10 та одам қўшмагунча ёздирмайди.\n"
        "🔹 <b>/majburoff</b> - Одам қўшиш мажбурияти ўчирилади.\n"
        "🔹 <b>/ruxsat</b> - Ответ ёки @ орқали белгиланган одамга рухсат берилади.\n"
        "🔹 <b>/kanal @username</b> - Каналга азо бўлишга мажбурлайди.\n"
        "🔹 <b>/kanaloff</b> - Каналга мажбур азо бўлишни ўчиради.\n"
        "🔹 <b>/top</b> - Кўп одам қўшган гуруҳ аъзоларини кўрсатади.\n"
        "🔹 <b>/cleangroup</b> - Барча ҳисобларни 0 қилади.\n"
        "🔹 <b>/count</b> - Сиз қўшган одамлар сонини кўрсатади.\n"
        "🔹 <b>/replycount</b> - Ответ қилинган фойдаланувчи неча одам қўшганини кўрсатади.\n"
        "🔹 <b>/cleanuser</b> - Ответ қилинган фойдаланувчи ҳисоби 0 қилинади.\n"
    )
    await update.message.reply_text(text, parse_mode="HTML")


app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("help", help))
app.add_handler(CommandHandler("id", id_berish))
app.add_handler(CommandHandler("majbur", majbur))
app.add_handler(CommandHandler("majburoff", majburoff))
app.add_handler(CommandHandler("kanal", kanal))
app.add_handler(CommandHandler("kanaloff", kanaloff))
app.add_handler(CommandHandler("ruxsat", ruxsat))
app.add_handler(CommandHandler("top", top))
app.add_handler(CommandHandler("count", count))
app.add_handler(CommandHandler("replycount", replycount))
app.add_handler(CommandHandler("cleangroup", cleangroup))
app.add_handler(CommandHandler("cleanuser", cleanuser))
app.add_handler(CommandHandler("tun", tun))
app.add_handler(CommandHandler("tunoff", tunoff))
app.add_handler(CallbackQueryHandler(majbur_callback, pattern="^majbur_"))
app.add_handler(
    CallbackQueryHandler(majbur_tekshir_callback,
                         pattern="^(odam_qoshdim|ruxsat_berish)$"))
app.add_handler(CallbackQueryHandler(kanal_callback, pattern="^kanal_azo$"))

app.add_handler(
    MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_goodbye))
app.add_handler(
    MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, welcome_goodbye))
app.add_handler(
    MessageHandler(filters.TEXT & (~filters.COMMAND), reklama_aniqlash))
app.add_handler(
    ChatMemberHandler(on_chat_member, ChatMemberHandler.CHAT_MEMBER))


# 🔒 Faqat private chat uchun komandalar menyusi
async def set_commands():
    await app.bot.set_my_commands(commands=[
        BotCommand("help", "Bot qo'llanmasi"),
        BotCommand("id", "Sizning ID’ingizni ko‘rsatadi"),
        BotCommand("tun", "Tun rejimini yoqish"),
        BotCommand("tunoff", "Tun rejimini o‘chirish"),
        BotCommand("majbur", "Majburiy odam qo‘shish soni"),
        BotCommand("majburoff", "Majburiy odam qo‘shishni o'chirish"),
        BotCommand("ruxsat", "Odamga barcha ruxsatlar berish"),
        BotCommand("kanal", "Majburiy kanalga a'zo bo'lish"),
        BotCommand("kanaloff", "Majburiy kanalga a'zo bo'lishni o'chirish"),
        BotCommand("top", "kop odam qo'shganlar ro'yxati"),
        BotCommand("cleangroup",
                   "Otvet qilingan odam qo'shganlar sonini nolga qaytarish"),
        BotCommand("count", "Siz qo'shgan odamlar soni"),
        BotCommand("replycount", "Otvet qilingan odam qo'shganlar soni"),
        BotCommand("tunoff", "Tun rejimini o‘chirish"),
    ],
                                  scope=BotCommandScopeAllPrivateChats())

import asyncio


async def botni_ishga_tushur():
    await set_commands()
    print("✅ Bot ishga tushdi...")
    await app.initialize()
    await app.start()
    await app.bot.set_webhook("https://telegram-bot-dwl4.onrender.com/webhook")



if __name__ == "__main__":
    start_web()
    asyncio.run(botni_ishga_tushur())


# 🔁 Tugmalar orqali foydalanuvchini blokdan chiqarish

# 🔁 Kanalga a’zo bo‘lganini tekshirib, foydalanuvchini yozishdan chiqarish

# 🔁 Kanalga a’zo bo‘lganini tekshirib, foydalanuvchini yozishdan chiqarish