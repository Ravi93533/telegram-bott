from telegram import Update, BotCommand, BotCommandScopeAllPrivateChats, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatMemberStatus
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ChatMemberHandler, ContextTypes, filters

def admin_add_link(bot_username: str) -> str:
    rights = [
        'delete_messages','restrict_members','invite_users',
        'pin_messages','manage_topics','manage_video_chats','manage_chat'
    ]
    rights_param = '+'.join(rights)
    return f"https://t.me/{bot_username}?startgroup&admin={rights_param}"

import threading
import os
import re
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from flask import Flask

# ----------- Small keep-alive web server -----------
app_flask = Flask(__name__)

@app_flask.route("/")
def home():
    return "Бот работает!"

def run_web():
    app_flask.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))

def start_web():
    threading.Thread(target=run_web, daemon=True).start()

# ----------- Config -----------
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

TOKEN = os.getenv("TOKEN") or "YOUR_TOKEN_HERE"

WHITELIST = {165553982, "Yunus1995"}
TUN_REJIMI = False
KANAL_USERNAME = None

MAJBUR_LIMIT = 0
FOYDALANUVCHI_HISOBI = defaultdict(int)
RUXSAT_USER_IDS = set()
BLOK_VAQTLARI = {}  # (chat_id, user_id) -> until_datetime (UTC)

# ✅ Полные разрешения на отправку (если это разрешено настройками группы)
FULL_PERMS = ChatPermissions(
    can_send_messages=True,
    can_send_audios=True,
    can_send_documents=True,
    can_send_photos=True,
    can_send_videos=True,
    can_send_video_notes=True,
    can_send_voice_notes=True,
    can_send_polls=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
    can_invite_users=True,
)

# Разрешения при блокировке (3 минуты): запрещаем писать, но оставляем приглашение пользователей
BLOCK_PERMS = ChatPermissions(
    can_send_messages=False,
    can_send_audios=False,
    can_send_documents=False,
    can_send_photos=False,
    can_send_videos=False,
    can_send_video_notes=False,
    can_send_voice_notes=False,
    can_send_polls=False,
    can_send_other_messages=False,
    can_add_web_page_previews=False,
    can_invite_users=True,
)

# Список нецензурных слов — НЕ ТРОГАТЬ (оставлено как в оригинале)
UYATLI_SOZLAR = {"am", "ammisan", "ammislar", "ammislar?", "ammisizlar", "ammisizlar?", "amsan", "ammisan?", "amlar", "amlatta", "amyalaq", "amyalar", "amyaloq", "amxor", "am yaliman", "am yalayman", "am latta", "aminga", "aminga ske", "aminga sikay", "asshole", "bastard", "biyundiami", "bitch", "blyat", "buynami", "buyingdi omi", "buyingni ami", "buyundiomi", "dalbayob", "damn", "debil", 
    "dick", "dolboyob", "durak", "eblan", "fuck", "fakyou", "fuckyou", "foxisha", "fohisha", "fucker", "gandon", "gandonmisan", "gandonmisan?", "gandonlar", "blya", "haromi", "huy", "haromilar", "horomi", "idinnaxxuy", "idinaxxuy", "idin naxuy", "idin naxxuy", 
    "isqirt", "jalap", "kal", "kot", "kotmislar", "kotmislar?", "kotmisizlar", "kotmisizlar?", "kotlar", "kotak", "kotmisan", "kotmisan?", "kotsan", "ko'tsan", "ko'tmisan", "ko't", "ko'tlar", "kotinga ske", "kotinga sikay", "kotinga", "ko'tinga", "kotingga", "kotvacha", "ko'tak", 
    "lanati", "lax", "motherfucker", "mudak", "naxxuy", "og'zingaskay", "og'zinga skay", "ogzingaskay", "otti qotagi", "otni qotagi", "horomilar", "huyimga", "huygami",
    "otti qo'tag'i", "ogzinga skay", "onagniomi", "onangniami", "pashol naxuy", "padarlanat", "lanat", "pasholnaxxuy", "pidor", 
    "poshol naxxuy", "posholnaxxuy", "poxxuy", "poxuy", "qanjik", "qanjiq", "qonjiq", "qotaq", "qotaqxor", "qo'taq", "qo'taqxo'r", 
    "qotagim", "kotagim", "qo'tag'im", "qotoqlar", "qo'toqlar", "qotag'im", "qotoglar", "qo'tog'lar", "qotagim", "sik", "sikaman", "skasizmi", "sikasizmi", "sikay", "sikalak", "sikish", "sikishish", "skay", 
    "slut", "soska", "suka", "tashak", "tashaq", "toshoq", "toshok", "xaromi", "xoramilar", "xoromi", "xoromilar", "ам", "аммисан", "аммисан?", "амсан", "амлар", "амлатта", "аминга", "амялак", "амялок", "амхўр", "амхур", "омин", "оминга", "ам ялиман", "ам ялайман", "искирт", "жалап", 
    "далбаёб", "долбоёб", "гандон", "гандонлар", "гандонмисан", "гандонмисан?", "нахуй", "иди нахуй", "иди наххуй", "идинахуй", "идинаххуй", "идин наххуй", "идиннаххуй", "кот", "котак", "кутагим", "қўтағим",
    "кут", "кутмисан", "кутмислар", "кутмисизлар", "кутмисизлар?", "кутмисан?", "кутсан", "кўтсан", "кутак", "кутлар", "кутингга", "кўт", "кўтлар", "кўтингга", "ланати", "нахуй", "наххуй", "огзинга скай", "огзингаскай", "онагниоми", "онагни оми",
    "онангниами", "онангни ами", "огзинга скей", "огзинга сикай", "отни кутаги", "пашол нахуй", "пашолнаххуй", "пидор", "пошол наххуй", "кўтмислар", "кўтмислар?", "кўтмисизлар?", 
    "похуй", "поххуй", "пошолнаххуй", "секис", "сикасиз", "сикай", "сикаман", "сикиш", "сикишиш", "сикишамиз", "скишамиз", "сикишаман", "скишаман", "сикишамизми?", "скишамизми?", "сикасизми", "скасизми", "скасизми?", "сикасизми?", "скасиз", "соска", "сука", "ташак", "ташақ", "тошок", 
    "тошоқ", "хароми", "ҳароми", "ҳороми", "қотақ", "ске", "ланат", "ланати", "падарланат", "қотақхор", "қўтақ", "ташақлар", "қўтоқлар", "кутак", "қўтақхўр", 
    "қанжик", "қанжиқ", "қонжиқ", "am", "amlatta", "amyalaq", "amyalar", "buÿingdi ami", "buyingdi omi", "buyingni ami", "buyindi omi", 
    "buynami", "biyindi ami", "skiy", "skay", "sikey", "sik", "kutagim", "skaman", "xuy", "xuramilar", "xuy", "xuyna", "skishaman", "skishamiz", "skishamizmi?", "sikishaman", "sikishamiz", "skey"}

# Ключевые слова/домены подозрительной игровой/inline-рекламы
SUSPECT_KEYWORDS = {"open game", "play", "играть", "открыть игру", "game", "cattea", "gamee", "hamster", "notcoin", "tap to earn", "earn", "clicker"}
SUSPECT_DOMAINS = {"cattea", "gamee", "hamster", "notcoin", "tgme", "t.me/gamee", "textra.fun", "ton"}

# ----------- Helpers -----------
async def is_admin(update: Update) -> bool:
    chat = update.effective_chat
    user = update.effective_user
    if not (chat and user):
        return False
    try:
        member = await update.get_bot().get_chat_member(chat.id, user.id)
        return member.status in ("administrator", "creator")
    except Exception as e:
        log.warning(f"is_admin error: {e}")
        return False

async def is_privileged_message(msg, bot) -> bool:
    """Разрешаем сообщения админов, создателя и от имени группы (sender_chat)."""
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
        log.warning(f"is_privileged_message error: {e}")
    return False

async def kanal_tekshir(user_id: int, bot) -> bool:
    global KANAL_USERNAME
    if not KANAL_USERNAME:
        return True
    try:
        member = await bot.get_chat_member(KANAL_USERNAME, user_id)
        return member.status in ("member", "creator", "administrator")
    except Exception as e:
        log.warning(f"kanal_tekshir error: {e}")
        return False

def matndan_sozlar_olish(matn: str):
    return re.findall(r"\b\w+\b", (matn or "").lower())

def add_to_group_kb(bot_username: str):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("➕ Добавить в группу", url=admin_add_link(bot_username))]]
    )

def has_suspicious_buttons(msg) -> bool:
    try:
        kb = msg.reply_markup.inline_keyboard if msg.reply_markup else []
        for row in kb:
            for btn in row:
                if getattr(btn, "callback_game", None) is not None:
                    return True
                u = getattr(btn, "url", "") or ""
                if u:
                    low = u.lower()
                    if any(dom in low for dom in SUSPECT_DOMAINS) or any(x in low for x in ("game", "play", "tgme")):
                        return True
                wa = getattr(btn, "web_app", None)
                if wa and getattr(wa, "url", None):
                    if any(dom in wa.url.lower() for dom in SUSPECT_DOMAINS):
                        return True
        return False
    except Exception:
        return False

# ----------- Commands -----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("➕ Добавить в группу", url=admin_add_link(context.bot.username))]]
    await update.effective_message.reply_text(
        "<b>ПРИВЕТ👋</b>\n"
        "Я <b>удаляю</b> из групп любые рекламные посты, ссылки, сообщения о входе/выходе и рекламу от вспомогательных ботов.\n\n"
        "Могу определить ваш <b>ID</b> профиля.\n\n"
        "Сделаю обязательным добавление людей в группу и подписку на канал (иначе писать нельзя) ➕\n\n"
        "Удаляю 18+ нецензурные слова и делаю многое другое 👨🏻‍✈\n\n"
        "Справка по командам 👉 /help\n\n"
        "Чтобы я работал, добавьте меня в группу и дайте <b>ПРАВА АДМИНА</b> 🙂\n\n"
        "Для связи👉 @Devona0107",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📌 <b>СПИСОК КОМАНД</b>\n\n"
        "🔹 <b>/id</b> — Показать ваш ID.\n"
        "🔹 <b>/tun</b> — Ночной режим (все новые сообщения обычных пользователей будут автоматически удаляться).\n"
        "🔹 <b>/tunoff</b> — Выключить ночной режим.\n"
        "🔹 <b>/ruxsat</b> — Выдать привилегию по reply.\n"
        "🔹 <b>/kanal @username</b> — Включить обязательную подписку на указанный канал.\n"
        "🔹 <b>/kanaloff</b> — Отключить обязательную подписку.\n"
        "🔹 <b>/majbur [3–25]</b> — Включить обязательное добавление людей в группу.\n"
        "🔹 <b>/majburoff</b> — Отключить обязательное добавление.\n"
        "🔹 <b>/top</b> — Топ участников по добавлениям.\n"
        "🔹 <b>/cleangroup</b> — Обнулить счётчики всех пользователей.\n"
        "🔹 <b>/count</b> — Сколько людей добавили вы.\n"
        "🔹 <b>/replycount</b> — По reply: сколько добавил указанный пользователь.\n"
        "🔹 <b>/cleanuser</b> — По reply: обнулить счётчик пользователя.\n"
    )
    await update.effective_message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)

async def id_berish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    user = update.effective_user
    await update.effective_message.reply_text(f"🆔 {user.first_name}, ваш Telegram ID: {user.id}")

async def tun(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global TUN_REJIMI
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Только для администраторов.")
    TUN_REJIMI = True
    await update.effective_message.reply_text("🌙 Ночной режим включён. Сообщения обычных пользователей будут удаляться.")

async def tunoff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global TUN_REJIMI
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Только для администраторов.")
    TUN_REJIMI = False
    await update.effective_message.reply_text("🌞 Ночной режим выключен.")

async def ruxsat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Только для администраторов.")
    if not update.effective_message.reply_to_message:
        return await update.effective_message.reply_text("Пожалуйста, ответьте (reply) на сообщение пользователя.")
    uid = update.effective_message.reply_to_message.from_user.id
    RUXSAT_USER_IDS.add(uid)
    await update.effective_message.reply_text(f"✅ Пользователю <code>{uid}</code> выдана привилегия.", parse_mode="HTML")

async def kanal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Только для администраторов.")
    global KANAL_USERNAME
    if context.args:
        KANAL_USERNAME = context.args[0]
        await update.effective_message.reply_text(f"📢 Обязательный канал: {KANAL_USERNAME}")
    else:
        await update.effective_message.reply_text("Пример: /kanal @username")

async def kanaloff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Только для администраторов.")
    global KANAL_USERNAME
    KANAL_USERNAME = None
    await update.effective_message.reply_text("🚫 Требование подписки на канал отключено.")

def majbur_klaviatura():
    rows = [[3, 5, 7, 10, 12], [15, 18, 20, 25, 30]]
    keyboard = [[InlineKeyboardButton(str(n), callback_data=f"set_limit:{n}") for n in row] for row in rows]
    keyboard.append([InlineKeyboardButton("❌ ОТМЕНИТЬ ❌", callback_data="set_limit:cancel")])
    return InlineKeyboardMarkup(keyboard)

async def majbur(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Только для администраторов.")
    global MAJBUR_LIMIT
    if context.args:
        try:
            val = int(context.args[0])
            if not (3 <= val <= 25):
                raise ValueError
            MAJBUR_LIMIT = val
            await update.effective_message.reply_text(
                f"✅ Лимит обязательных приглашений: <b>{MAJBUR_LIMIT}</b>",
                parse_mode="HTML"
            )
        except ValueError:
            await update.effective_message.reply_text(
                "❌ Неверное значение. Допустимый диапазон: <b>3–25</b>. Например: <code>/majbur 10</code>",
                parse_mode="HTML"
            )
    else:
        await update.effective_message.reply_text(
            "👥 Сколько людей нужно обязательно добавить в группу? 👇\n"
            "Не обязательно — /majburoff",
            reply_markup=majbur_klaviatura()
        )

async def on_set_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.callback_query.answer("Только для администраторов!", show_alert=True)
    q = update.callback_query
    await q.answer()
    data = q.data.split(":", 1)[1]
    global MAJBUR_LIMIT
    if data == "cancel":
        return await q.edit_message_text("❌ Отменено.")
    try:
        val = int(data)
        if not (3 <= val <= 25):
            raise ValueError
        MAJBUR_LIMIT = val
        await q.edit_message_text(f"✅ Лимит установлен: <b>{MAJBUR_LIMIT}</b>", parse_mode="HTML")
    except Exception:
        await q.edit_message_text("❌ Неверное значение.")

async def majburoff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Только для администраторов.")
    global MAJBUR_LIMIT
    MAJBUR_LIMIT = 0
    await update.effective_message.reply_text("🚫 Обязательное добавление людей отключено.")

async def top_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Только для администраторов.")
    if not FOYDALANUVCHI_HISOBI:
        return await update.effective_message.reply_text("Пока никто никого не добавил.")
    items = sorted(FOYDALANUVCHI_HISOBI.items(), key=lambda x: x[1], reverse=True)[:100]
    lines = ["🏆 <b>ТОП по количеству приглашённых</b> (TOP 100):"]
    for i, (uid, cnt) in enumerate(items, start=1):
        lines.append(f"{i}. <code>{uid}</code> — {cnt} чел.")
    await update.effective_message.reply_text("\n".join(lines), parse_mode="HTML")

async def cleangroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Только для администраторов.")
    FOYDALANUVCHI_HISOBI.clear()
    RUXSAT_USER_IDS.clear()
    await update.effective_message.reply_text("🗑 Все счётчики и привилегии сброшены.")

async def count_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    cnt = FOYDALANUVCHI_HISOBI.get(uid, 0)
    if MAJBUR_LIMIT > 0:
        qoldi = max(MAJBUR_LIMIT - cnt, 0)
        await update.effective_message.reply_text(f"📊 Вы пригласили {cnt} чел. Осталось: {qoldi}.")
    else:
        await update.effective_message.reply_text(f"📊 Вы пригласили {cnt} чел. (Обязательное добавление выключено)")

async def replycount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Только для администраторов.")
    msg = update.effective_message
    if not msg.reply_to_message:
        return await msg.reply_text("Пожалуйста, сделайте reply на сообщение нужного пользователя.")
    uid = msg.reply_to_message.from_user.id
    cnt = FOYDALANUVCHI_HISOBI.get(uid, 0)
    await msg.reply_text(f"👤 <code>{uid}</code> пригласил(а) {cnt} чел.", parse_mode="HTML")

async def cleanuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Только для администраторов.")
    msg = update.effective_message
    if not msg.reply_to_message:
        return await msg.reply_text("Пожалуйста, сделайте reply на сообщение пользователя, которого нужно обнулить.")
    uid = msg.reply_to_message.from_user.id
    FOYDALANUVCHI_HISOBI[uid] = 0
    RUXSAT_USER_IDS.discard(uid)
    await msg.reply_text(f"🗑 Счётчик пользователя <code>{uid}</code> обнулён (привилегия снята).", parse_mode="HTML")

async def kanal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    if not KANAL_USERNAME:
        return await q.edit_message_text("⚠️ Канал не настроен.")
    try:
        member = await context.bot.get_chat_member(KANAL_USERNAME, user_id)
        if member.status in ("member", "administrator", "creator"):
            # Полные права (в рамках разрешений группы)
            try:
                await context.bot.restrict_chat_member(
                    chat_id=q.message.chat.id,
                    user_id=user_id,
                    permissions=FULL_PERMS,
                )
            except Exception:
                pass
            await q.edit_message_text("✅ Подписка подтверждена. Теперь вы можете писать в группе.")
        else:
            await q.edit_message_text("❌ Вы ещё не подписаны на канал.")
    except Exception:
        await q.edit_message_text("⚠️ Ошибка проверки. Некорректный username канала или бот не является участником канала.")

async def on_check_added(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    # Нажимать может только сам пользователь, получивший предупреждение
    data = q.data
    if ":" in data:
        try:
            owner_id = int(data.split(":", 1)[1])
        except ValueError:
            owner_id = None
        if owner_id and owner_id != uid:
            return await q.answer("Эта кнопка не для вас!", show_alert=True)
    cnt = FOYDALANUVCHI_HISOBI.get(uid, 0)
    if uid in RUXSAT_USER_IDS or (MAJBUR_LIMIT > 0 and cnt >= MAJBUR_LIMIT):
        try:
            await context.bot.restrict_chat_member(
                chat_id=q.message.chat.id,
                user_id=uid,
                permissions=FULL_PERMS,
            )
        except Exception:
            pass
        BLOK_VAQTLARI.pop((q.message.chat.id, uid), None)
        await q.edit_message_text("✅ Требование выполнено! Теперь вы можете писать в группе.")
    else:
        qoldi = max(MAJBUR_LIMIT - cnt, 0)
        await q.edit_message_text(f"❌ Недостаточно приглашений. Осталось: {qoldi}.")

async def on_grant_priv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    chat = q.message.chat if q.message else None
    user = q.from_user
    if not (chat and user):
        return await q.answer()
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status not in ("administrator", "creator"):
            return await q.answer("Привилегии может выдавать только администратор!", show_alert=True)
    except Exception:
        return await q.answer("Ошибка проверки.", show_alert=True)
    await q.answer()
    try:
        target_id = int(q.data.split(":", 1)[1])
    except Exception:
        return await q.edit_message_text("❌ Неверные данные.")
    RUXSAT_USER_IDS.add(target_id)
    await q.edit_message_text(f"🎟 Пользователю <code>{target_id}</code> выдана привилегия. Теперь он(а) может писать.", parse_mode="HTML")

# ----------- Filters -----------
async def reklama_va_soz_filtri(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not msg.chat or not msg.from_user:
        return
    # Админы/создатель/сообщения от имени чата — пропускаем
    if await is_privileged_message(msg, context.bot):
        return
    # Белый список
    if msg.from_user.id in WHITELIST or (msg.from_user.username and msg.from_user.username in WHITELIST):
        return
    # Ночной режим
    if TUN_REJIMI:
        try:
            await msg.delete()
        except:
            pass
        return
    # Проверка подписки на канал
    if not await kanal_tekshir(msg.from_user.id, context.bot):
        try:
            await msg.delete()
        except:
            pass
        kb = [
            [InlineKeyboardButton("✅ Я подписался(ась)", callback_data="kanal_azo")],
            [InlineKeyboardButton("➕ Добавить в группу", url=admin_add_link(context.bot.username))]
        ]
        await context.bot.send_message(
            chat_id=msg.chat_id,
            text=f"⚠️ {msg.from_user.first_name}, вы не подписаны на {KANAL_USERNAME}!",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    text = msg.text or msg.caption or ""
    entities = msg.entities or msg.caption_entities or []

    # Сообщение через inline-бота — часто игровая реклама
    if getattr(msg, "via_bot", None):
        try:
            await msg.delete()
        except:
            pass
        await context.bot.send_message(
            chat_id=msg.chat_id,
            text="⚠️ Реклама через inline-ботов запрещена!",
            reply_markup=add_to_group_kb(context.bot.username)
        )
        return

    # Кнопки с играми/web-app/URL — блокируем
    if has_suspicious_buttons(msg):
        try:
            await msg.delete()
        except:
            pass
        await context.bot.send_message(
            chat_id=msg.chat_id,
            text="⚠️ Реклама с игровыми/веб-app кнопками запрещена!",
            reply_markup=add_to_group_kb(context.bot.username)
        )
        return

    # Рекламные тексты про игры
    low = text.lower()
    if any(k in low for k in SUSPECT_KEYWORDS):
        try:
            await msg.delete()
        except:
            pass
        await context.bot.send_message(
            chat_id=msg.chat_id,
            text="⚠️ Игровая реклама запрещена!",
            reply_markup=add_to_group_kb(context.bot.username)
        )
        return

    # Сообщения от ботов с game/ссылками
    if getattr(msg.from_user, "is_bot", False):
        has_game = bool(getattr(msg, "game", None))
        has_url_entity = any(ent.type in ("text_link", "url", "mention") for ent in entities)
        has_url_text = any(x in low for x in ("t.me","telegram.me","http://","https://","www.","youtu.be","youtube.com"))
        if has_game or has_url_entity or has_url_text:
            try:
                await msg.delete()
            except:
                pass
            await context.bot.send_message(
                chat_id=msg.chat_id,
                text="⚠️ Реклама/ссылки или game от ботов запрещены!",
                reply_markup=add_to_group_kb(context.bot.username)
            )
            return

    # Скрытые или явные ссылки
    for ent in entities:
        if ent.type in ("text_link", "url", "mention"):
            url = getattr(ent, "url", "") or ""
            if url and ("t.me" in url or "telegram.me" in url or "http://" in url or "https://" in url):
                try:
                    await msg.delete()
                except:
                    pass
                await context.bot.send_message(
                    chat_id=msg.chat_id,
                    text=f"⚠️ {msg.from_user.first_name}, отправка скрытых ссылок запрещена!",
                    reply_markup=add_to_group_kb(context.bot.username)
                )
                return

    if any(x in low for x in ("t.me","telegram.me","@","www.","https://youtu.be","http://","https://")):
        try:
            await msg.delete()
        except:
            pass
        await context.bot.send_message(
            chat_id=msg.chat_id,
            text=f"⚠️ {msg.from_user.first_name}, реклама/ссылки запрещены!",
            reply_markup=add_to_group_kb(context.bot.username)
        )
        return

    # Нецензурная лексика (словарь не меняли)
    sozlar = matndan_sozlar_olish(text)
    if any(s in UYATLI_SOZLAR for s in sozlar):
        try:
            await msg.delete()
        except:
            pass
        await context.bot.send_message(
            chat_id=msg.chat_id,
            text=f"⚠️ {msg.from_user.first_name}, мат в группе запрещён!",
            reply_markup=add_to_group_kb(context.bot.username)
        )
        return

# Учёт добавивших новых участников и удаление служебных сообщений
async def on_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    adder = msg.from_user
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

# Фильтр обязательных добавлений — недостача => блок на 3 минуты
async def majbur_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if MAJBUR_LIMIT <= 0:
        return
    msg = update.effective_message
    if not msg or not msg.from_user:
        return
    if await is_privileged_message(msg, context.bot):
        return

    uid = msg.from_user.id

    # Если пользователь ещё в блоке — удаляем сообщение молча
    now = datetime.now(timezone.utc)
    key = (msg.chat_id, uid)
    until_old = BLOK_VAQTLARI.get(key)
    if until_old and now < until_old:
        try:
            await msg.delete()
        except:
            pass
        return
    if uid in RUXSAT_USER_IDS:
        return

    cnt = FOYDALANUVCHI_HISOBI.get(uid, 0)
    if cnt >= MAJBUR_LIMIT:
        return

    # Удаляем сообщение
    try:
        await msg.delete()
    except:
        return

    # Блок на 3 минуты
    until = datetime.now(timezone.utc) + timedelta(minutes=3)
    BLOK_VAQTLARI[(msg.chat_id, uid)] = until
    try:
        await context.bot.restrict_chat_member(
            chat_id=msg.chat_id,
            user_id=uid,
            permissions=BLOCK_PERMS,
            until_date=until
        )
    except Exception as e:
        log.warning(f"Restrict failed: {e}")

    qoldi = max(MAJBUR_LIMIT - cnt, 0)
    kb = [
        [InlineKeyboardButton("✅ Я добавил(а) людей", callback_data=f"check_added:{uid}")],
        [InlineKeyboardButton("🎟 Выдать привилегию", callback_data=f"grant:{uid}")],
        [InlineKeyboardButton("➕ Добавить в группу", url=admin_add_link(context.bot.username))],
        [InlineKeyboardButton("⏳ Блок на 3 минуты", callback_data="noop")]
    ]
    await context.bot.send_message(
        chat_id=msg.chat_id,
        text=f"⚠️ Чтобы писать в группе, нужно пригласить {MAJBUR_LIMIT} человек(а)! Осталось: {qoldi}.",
        reply_markup=InlineKeyboardMarkup(kb)
    )

# ----------- Setup -----------
async def set_commands(app):
    await app.bot.set_my_commands(
        commands=[
            BotCommand("start", "Информация о боте"),
            BotCommand("help", "Справка по боту"),
            BotCommand("id", "Ваш ID"),
            BotCommand("count", "Сколько вы пригласили"),
            BotCommand("top", "ТОП-100 приглашений"),
            BotCommand("replycount", "(reply) сколько пригласил пользователь"),
            BotCommand("majbur", "Установить лимит обязательных приглашений (3–25)"),
            BotCommand("majburoff", "Отключить обязательные приглашения"),
            BotCommand("cleangroup", "Сбросить счётчики всем"),
            BotCommand("cleanuser", "(reply) сбросить счётчик пользователю"),
            BotCommand("ruxsat", "(reply) выдать привилегию"),
            BotCommand("kanal", "Настроить обязательный канал"),
            BotCommand("kanaloff", "Отключить обязательный канал"),
            BotCommand("tun", "Включить ночной режим"),
            BotCommand("tunoff", "Выключить ночной режим"),
        ],
        scope=BotCommandScopeAllPrivateChats()
    )

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
    app.add_handler(CallbackQueryHandler(on_check_added, pattern=r"^check_added(?::\d+)?$"))
    app.add_handler(CallbackQueryHandler(on_grant_priv, pattern=r"^grant:"))
    app.add_handler(CallbackQueryHandler(lambda u,c: u.callback_query.answer(""), pattern=r"^noop$"))

    # Events & Filters
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_new_members))
    media_filters = (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL | filters.ANIMATION | filters.VOICE | filters.VIDEO_NOTE | filters.GAME)
    app.add_handler(MessageHandler(media_filters & (~filters.COMMAND), majbur_filter), group=-1)
    app.add_handler(MessageHandler(media_filters & (~filters.COMMAND), reklama_va_soz_filtri))

    app.post_init = set_commands
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

async def on_my_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        st = update.my_chat_member.new_chat_member.status
    except Exception:
        return
    if st in (ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED):
        me = await context.bot.get_me()
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(
            '🔐 Сделать бота админом', url=admin_add_link(me.username)
        )]])
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=(
                    '⚠️ Бот пока *не администратор*.\n'
                    'Пожалуйста, дайте права администратора по кнопке ниже — тогда все функции будут работать.'
                ),
                reply_markup=kb,
                parse_mode='Markdown'
            )
        except Exception:
            pass
