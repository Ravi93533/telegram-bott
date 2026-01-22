from telegram import Chat, Message, Update, BotCommand, BotCommandScopeAllPrivateChats, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ChatMemberHandler, ContextTypes, filters

import threading
import os
import re
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import html
import ssl
from urllib.parse import urlparse, urlunparse, urlencode, parse_qsl

from flask import Flask

# --- New (Postgres) ---
import asyncio
import json
from typing import List, Optional

try:
    import asyncpg
except ImportError:
    asyncpg = None  # handled below with a log warning

# ---------------------- Linked channel helpers ----------------------
def _extract_forward_origin_chat(msg: Message):
    fo = getattr(msg, "forward_origin", None)
    if fo is not None:
        chat = getattr(fo, "chat", None) or getattr(fo, "from_chat", None)
        if chat is not None:
            return chat
    return getattr(msg, "forward_from_chat", None)



# ---- Linked channel cache helpers (added) ----
_GROUP_LINKED_ID_CACHE: dict[int, int | None] = {}

async def _get_linked_id(chat_id: int, bot) -> int | None:
    """Fetch linked_chat_id reliably using get_chat (cached)."""
    if chat_id in _GROUP_LINKED_ID_CACHE:
        return _GROUP_LINKED_ID_CACHE[chat_id]
    try:
        chat = await bot.get_chat(chat_id)
        linked_id = getattr(chat, "linked_chat_id", None)
        _GROUP_LINKED_ID_CACHE[chat_id] = linked_id
        return linked_id
    except Exception:
        _GROUP_LINKED_ID_CACHE[chat_id] = None
        return None
# ---- end helpers ----
async def is_linked_channel_autoforward(msg: Message, bot) -> bool:
    """
    TRUE faqat guruhning bog'langan kanalidan avtomatik forward bo'lgan postlar uchun.
    - msg.is_automatic_forward True
    - get_chat(chat_id).linked_chat_id mavjud
    - va (sender_chat.id == linked_id) yoki (forward_origin chat.id == linked_id)
    - origin yashirilgan bo‘lsa ham fallback True (is_automatic_forward bo‘lsa)
    """
    try:
        if not getattr(msg, "is_automatic_forward", False):
            return False
        linked_id = await _get_linked_id(msg.chat_id, bot)
        if not linked_id:
            return False
        sc = getattr(msg, "sender_chat", None)
        if sc and getattr(sc, "id", None) == linked_id:
            return True
        fwd_chat = _extract_forward_origin_chat(msg)
        if fwd_chat and getattr(fwd_chat, "id", None) == linked_id:
            return True
        # Fallback: origin yashirilgan bo‘lishi mumkin
        return True
    except Exception:
        return False

# ---------------------- Small keep-alive web server ----------------------
app_flask = Flask(__name__)

@app_flask.route("/")
def home():
    return "Bot ishlayapti!"

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

# ✅ To'liq yozish ruxsatlari (guruh sozlamalari ruxsat bergan taqdirda)
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

# Blok uchun ruxsatlar (1 daqiqa): faqat yozish yopiladi, odam qo'shishga ruxsat qoldiriladi
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

# So'kinish lug'ati
UYATLI_SOZLAR = {"апчхуй", "архипиздрит", "ахуй", "ахулиард", "беден как Адам, и хуя прикрыть нечем", "без пизды", "бля", "блядво", "блядёшка", "блядина", "блядища",
    "блядки", "блядовать", "блядовитый", "блядоёбина", "блядский", "блядство", "блядствовать", "блядун", "блядь",
    "блядькать", "блядькнуть", "бляха-муха", "босый хуй", "босым хуем около голой пизды шутки не шутят",
    "буква «ю» — по хую", "был бы хуй, а подхуйки найдутся",
    "в ахуе", "в два хуя", "в душе не ебу", "в еблет наклацать", "в жопу ёбаный", "в пизду",
    "в рай въехать на чужом хую", "в рот ебаться", "в хуй дует", "в хуй дышит", "в хуй не всраться", "в хуй не дуть",
    "в хуй не ставить", "в хуй не упереться", "веселоебучесть", "веселоебучий", "весь в поте и хуй в роте",
    "весь в поту и хуй во рту", "вешать лапшу на хуй", "взъёб", "взъебать", "взъёбка", "взъебти", "взъёбывать",
    "влындить хуй", "во рту мухи ебутся", "водить хуем по губам", "война — хуйня, главное — манёвры", "вола ебать",
    "волоёб", "волоёбство", "вот и весь хуй", "вот те нате — хуй в томате!", "врубить съебаторы",
    "всё в ажуре, а хуй на абажуре", "всё пучком и пизда торчком", "вхуяриться", "въёб", "въебать", "въебаться",
    "въебашить", "въебенить", "въёбка", "въёбывать", "въехать в рай на чужом хую", "выблядок", "выебанный",
    "выебать", "выебаться", "выебина", "выёбистый", "выебнуть", "выебнуться", "выебон", "выебонщик", "выебсти",
    "выебти", "выёбывать", "выёбываться", "выеть", "выпиздеться", "выпиздить",
    "гавкнуть пиздой", "где совесть была, там хуй вырос", "говно", "головка от хуя", "головотяп",
    "голодная пизда", "голосуй — не голосуй, всё равно получишь хуй", "голохуевка", "горит пизда",
    "дать в еблетку", "дать пизды", "дать по ебалу", "дать по пизде мешалкой", "девятый хуй без соли доедать",
    "дневальный! подай станок ебальный!", "до пизды", "до хуища", "до хуя", "довыёбываться", "доёб", "доебать",
    "доебаться", "доёбистый", "доёбка", "доебсти", "доебти", "доёбчивость", "доёбчивый", "доёбщик", "доёбывать",
    "доёбываться", "доигрался хуй на скрипке", "долбоёб", "долбоебизм", "долбоёбина", "долбоёбище", "долбоёбский",
    "долбоёбство", "допиздеться", "дохулион", "дохуя", "драпиздон", "драпиздончик",
    "друг дружку ебут и деньги в кружку кладут", "дуроёб", "дядеёб",
    "ёб", "ёб вашу мать", "ёб иху мать", "ёб твою мать", "ёб твоя мать", "еба", "ёба", "ебабельность",
    "ебабельный", "ебак", "ебака", "Ебаков", "ебал", "ебал я тебя в грызло", "ебала", "ебала жаба гадюку",
    "ебалай", "ебалайствовать", "ёбалды", "ебало", "ебало завали!", "ебало на ноль!", "ебало офнуть",
    "ебало раскурочить", "ебало сверни!", "ебало свернуть", "ебальная", "ебальник", "ебальник начистить",
    "ебальник просрать", "ебальник разрисовать", "ебальничек", "ебальный", "ебальня", "ебальце", "ебан", "ебанарий",
    "ебанат", "ебанатик", "ебанашка", "ебание", "ебанизм", "ебанина", "ебанистика", "ебанистический", "ёбанный",
    "ебано", "ёбаногандонный хуепедераст", "ебаноид", "ебанутость", "ебанутый", "ебануть", "ебануть в бороду",
    "ебануться", "ебанушка", "ебаный", "ёбаный", "ёбаный в жопу", "ёбаный в рот", "ёбаный насос", "ёбаный покос",
    "ёбаный стос", "ёбаный стыд", "ёбаный шашлык", "ёбань", "ебанье", "ебанько", "ебарёк", "ебарёчек", "ебаришка", "ебаришко", "ёбарь",
    "ёбарь-перехватчик", "ебати", "ебатись", "ебаторий", "ебатура", "ебать", "ебать вола", "ебать и резать",
    "ебать мозги", "ебать мой лысый череп", "ебать мой хуй ментовской жопой", "ебать раком", "ебаться",
    "ебаться в телевизор", "ебач", "ебашить", "ебашиться", "ебейший", "ебель", "ебельник", "ебёна мать",
    "ебёна темя", "ебенить", "ебеный", "ебёный", "ебеня", "еби его мать", "еби её мать", "ебись о плетень",
    "ебись оно всё конём", "ебись твою в ноздрю", "ебит твою мать", "ебический", "Ебишка", "ёбка", "ёбкий",
    "ёбко", "ёбкость", "еблан", "ебланить", "ебланище", "ебланский", "еблет", "еблетень", "еблетка", "еблец",
    "еблецо", "ебливенький", "ебливость", "ебливый", "еблина", "еблито", "еблишко", "еблишко прикрой!",
    "еблище", "ебло", "ебло стянуть", "ебловать", "ёблышко", "ебля", "ёбля", "ёбнутый", "ебнуть", "ёбнуть",
    "ёбнуть по фазе", "ёбнуть фазу", "ёбнуться", "ебня", "ебобо", "ебовый", "ебоглазить", "ебомый", "ебосос",
    "ебосос расхлестать", "ебота", "ебота на еботе", "ёботность", "ёботный", "еботня", "ебошить", "ебошиться",
    "ёбс", "ёбс-переёбс", "ёбство", "ебсти", "ебстись", "ебти", "ебтись", "ёбу даться", "ебукать", "ебуки",
    "ебун", "ебунеть", "ебунец", "ебунок", "ебунья", "ебур", "ебут вашу мать", "ебут и фамилию не спрашивают",
    "ебучесть", "ебучий", "ебучка", "ебушатник", "ебушатник прикрыть", "ебушатня", "ёбушки-воробушки",
    "ёбфренд", "ёбче", "ёбши", "ёбывать", "ебырок", "ёбырь", "ёбыч", "ёпт", "ёпта", "ёпть",
    "если бы у бабушки был хуй, то она была бы дедушкой", "естись", "етись", "етить", "еть", "еться",
    "жевать большой хуище", "жевать хуи", "жрать нехуя и съебаться некуда",
    "за всю хуйню", "за каким хуем", "за не хуй делать", "за три пизды", "за хуем", "забить хуй",
    "заблядовать", "заёб", "заёба", "заёбанный", "заебательский", "заебато", "заебатый", "заебать",
    "заебаться", "заебашить", "заебенить", "заебенить по гражданке", "заебёшься пыль глотать", "заёбисто",
    "заёбистый", "заебись", "заебок", "заебти", "заебу — больно ходить будет", "заебунеть", "заёбушка",
    "заебца", "заебцовый", "заёбывать", "заеть", "закрыть пиздак", "залупистый", "запиздеть", "запиздеться",
    "запиздонить", "запиздюливать", "запиздюривать", "запиздючить", "заработать хуем по затылку",
    "засандалить хуй", "захуевертить", "захуёвничать", "захуяривать", "захуярить", "захуячить", "захуячиться",
    "зачесалася пизда", "защеканец", "заябать", "збс", "здрахуйте", "злоебучесть", "злоебучий",
    "и в хуй не дуть", "и рыбку съесть, и на хуй сесть", "ибиомать", "иди на хуй", "идти на хуй",
    "изволоёбить", "изъёб", "изъебать", "изъеблася", "изъебнуться", "изъебтись", "или рыбку съесть, или на хуй сесть", "Викисловарь:Инкубатор/нахуйник", "испиздеться", "испиздить", "исхуёвничаться", "исхуярить", "исхуячить",
    "к ебене матери", "к ебеней матери", "к ебеням", "к херам собачьим", "к хуям", "к хуям собачьим",
    "каждый кулик на своём хую велик", "как из пизды на лыжах", "как не хуй делать", "как у латыша — хуй да душа",
    "как хуем сбрило", "как хуем сдуло", "как хуй с плеч упал", "какая пизда тебя родила", "какого хуя",
    "картавый рыжий хуй", "кидать через хуй", "килька в томате да пизда в халате", "кинуть через хуй",
    "класть крепкий хуй", "кого ебёт чужое горе", "колдоёбина", "кому хуй, а мне всегда два!",
    "коноёбить", "коноёбиться", "короёбочка", "косоёбить", "кремлядь", "крыть хуями", "кусай за хуй!", "къебенизация",
    "ложь, пиздёж и провокация", "луркоёб", "луркофаг",
    "мамкоёб", "мамоёб", "мандец", "мать его ети", "мать их ёб", "мать иху ёб", "мать твою ёб",
    "мать твою распроеби", "мёртвого за хуй тянуть", "милипиздрический", "мозги ебать",
    "мозгоблуд", "мозгоёб", "мозгоебатель", "мозгоебательство", "мозгоёбка", "мозгоёбство",
    "мозгоёбствовать", "молодой хуёк", "мудоёб",
    "на воре и шапка пизженая", "на кой хуй", "на моих золотых полчаса как спиздили",
    "на одном месте не уебёшь — надо перетаскивать", "на отъебись", "на пизду надеяться",
    "на хуище", "на хуй", "на хуй — не на гвоздь", "на хуй нужен", "на хуй нужно", "на хуй с пляжа",
    "на хуй твоя жопа хороша", "на хую вертеть", "на хуя", "на хуях таскать", "навернуть еблет",
    "навешать пиздюлей", "навставлять пиздюлей", "надавать пиздюлей", "наёб", "наебалово",
    "наебательство", "наебать", "наебаться", "наебашить", "наебениваться", "наебениться",
    "наебизнес", "наёбка", "наебнуть", "наебнуться", "наебнуться головой", "наеборезиться",
    "наеборезываться", "наебти", "наебтись", "наёбщик", "наёбщица", "наёбывать", "наихуёвейший",
    "напиздеть", "напиздеться", "напиздить", "напудрить пизду", "нас ебут, а мы крепчаем",
    "настоебать", "настопиздеть", "нах", "нахохлить пизду", "нахуевертить", "нахуй", "нахуя",
    "нахуярить", "нахуяриться", "нахуячиваться", "нахуячить", "нахуячиться", "начистить ебальник",
    "не въебаться", "не ебаться", "не еби гусей", "не наебёшь ― не проживёшь", "не по хуйне",
    "не пришей к пизде рукав", "не смеши пизду, она и так смешная", "не ставить ни в хуй",
    "не считать хуй за мясо", "не хочешь кулеш, хуй ешь", "не хуй", "не хуй делать",
    "не хуй делать, пол топтать", "не хуй собачий", "не хуя", "невзъебенный", "невъебенно",
    "невъебенность", "невъебенный", "недоёб", "неебабельность", "неебабельный", "неебёный",
    "неебический", "нех", "нехуёвый", "нехуй", "нехуйно", "нехуйный", "нехуя",
    "ни бороды, ни усов, ни на хую волосов", "ни в пизду, ни в Красную Армию",
    "ни в хуй не ставить", "ни за хуй", "ни за хуй собачий", "ни с хуя", "ни хуя",
    "ни хуя себе", "ни хуя себе уха", "ни хуя уха", "нищеёб", "ноль целых, хуй десятых",
    "носим ношеное, ебём брошенное",
    "о пизде ни слова", "обложить хуями", "обувать пизду в лапти", "объёб", "объебать",
    "объебаться", "объебашивать", "объебашить", "объеблан", "объебон", "объебос", "объебошивать",
    "объебошить", "объёбывать", "овердохуя", "овцеёб", "один хуй", "однохуйственно",
    "одолбоёбиться", "опездал", "опездол", "опизденевать", "опизденеть", "опизденительность",
    "опизденительный", "опиздоволоситься", "опиздохуительный", "опиздюливаемый",
    "опиздюливать", "опиздюливаться", "опиздюлить", "опиздюлиться", "ослоёб", "остаться с хуем",
    "остоебенить", "остопиздеть", "остопиздить", "остохуеть", "от не хуй делать", "от хуя кончики", "от хуя уши", "отпиздеться", "отпиздить",
    "отпиздиться", "отпиздохать", "отпиздякать", "отпиздячить", "отхватить пиздюлей",
    "отхуесосить", "отхуякать", "отхуярить", "отхуячивать", "отхуячить", "отъебать",
    "отъебаться", "отъебнуть", "отъебошить", "отъебти", "отъебукать", "отъёбываться",
    "охуев", "охуевание", "охуевать", "охуевоз", "охуевший", "охуение", "охуенно",
    "охуенность", "охуенный", "охуенский", "охуенчик", "охуетительный", "охуеть",
    "охуительно", "охуительный", "охуй", "охулиард", "охулион", "охуячивать", "охуячить",
    "пёзды", "передок", "переёб", "переебать", "переебти", "перепиздеть", "перехуярить",
    "перехуячить", "персидского царя хуилище", "Пидрахуй", "пизда", "пизда горит",
    "пизда на ободах", "пизда нестроевая", "пизда пилоткой", "пизда рулю",
    "пизда с ушами", "пизда чешется", "пиздабол", "пиздак", "пиздануть",
    "пиздануться", "пиздарики", "пиздарики на воздушном шарике", "пиздатее", "пиздато",
    "пиздатый", "пиздёж", "пизделушка", "пиздёнка", "пиздёночка", "пиздёныш",
    "пиздёнышка", "пиздень", "пиздеть", "пиздеться", "пиздец", "пиздец подкрался незаметно",
    "пиздецки", "пиздецкий", "пиздецовый", "пиздёшечка", "пиздёшка", "пизди, пизди: приятно слушать",
    "пиздий", "пиздиловка", "пиздить", "пиздиться", "пиздишка", "пиздища", "пиздище",
    "пиздливый", "пиздлявый", "пиздлявый ящик", "пиздня", "пиздоблядство", "пиздобол",
    "пиздоболить", "пиздобольство", "пиздобратия", "пиздовать", "пиздоглазый",
    "пиздоделие", "пиздодельный", "пиздоёбство", "пиздой мух ловить", "пиздой накрыться",
    "пиздоквак", "пиздолиз", "пиздолизка", "пиздомудство", "пиздопроёбище",
    "пиздопротивный", "пиздорванец", "пиздорванец хуев", "пиздорванка", "пиздорез",
    "пиздоремонтник", "пиздоремонтничек", "пиздос", "пиздосий", "пиздострадалец",
    "пиздохаться", "пиздоход", "пиздохранилище", "пиздошить", "пизду в лапти обувать",
    "пиздуй", "пиздун", "пиздуна запускать", "пиздуна запустить", "пиздушечка", "пиздушка",
    "пизды дать", "пиздык", "пиздюк", "пиздюлей вложить", "пиздюлей навешать",
    "пиздюлей навставлять", "пиздюлей отхватить", "пиздюлина", "пиздюль", "пиздюря",
    "пиздюхать", "пиздюшка", "пиздякнуться", "пиздянка", "пиздятина", "пиздятинка",
    "пиздячить", "пиздящий", "пизже", "пизженый", "пинать хуи", "пинать хуй",
    "по ебалу получить", "по пизде мешалкой", "по пизде мешалкой словить", "по хую",
    "повъёбывать", "повыёбываться", "под ногти выебать", "подарок — из пизды огарок",
    "подзаебать", "подзаебаться", "подзаебти", "подохуевший", "подохуеть", "подпизживать",
    "подхуек", "подъёб", "подъебать", "подъебаться", "подъебаш", "Подъебишкин",
    "подъёбка", "подъебнуть", "подъебон", "подъебончик", "подъебушка", "подъёбщик",
    "подъёбывать", "Подъебышкин", "поебатор", "поебать", "поёбать", "поебаться",
    "поебень", "поёбка", "поебок", "поебота", "поеботина", "поебстись", "поебти",
    "поебтись", "поебусенка", "поебуха", "от не хуй делать", "от хуя кончики", "от хуя уши", "отпиздеться", "отпиздить",
    "отпиздиться", "отпиздохать", "отпиздякать", "отпиздячить", "отхватить пиздюлей",
    "отхуесосить", "отхуякать", "отхуярить", "отхуячивать", "отхуячить",
    "отъебать", "отъебаться", "отъебнуть", "отъебошить", "отъебти", "отъебукать",
    "отъёбываться", "охуев", "охуевание", "охуевать", "охуевоз", "охуевший",
    "охуение", "охуенно", "охуенность", "охуенный", "охуенский", "охуенчик",
    "охуетительный", "охуеть", "охуительно", "охуительный", "охуй", "охулиард",
    "охулион", "охуячивать", "охуячить", "пёзды", "передок", "переёб", "переебать",
    "переебти", "перепиздеть", "перехуярить", "перехуячить", "персидского царя хуилище",
    "Пидрахуй", "пизда", "пизда горит", "пизда на ободах", "пизда нестроевая",
    "пизда пилоткой", "пизда рулю", "пизда с ушами", "пизда чешется", "пиздабол",
    "пиздак", "пиздануть", "пиздануться", "пиздарики", "пиздарики на воздушном шарике",
    "пиздатее", "пиздато", "пиздатый", "пиздёж", "пизделушка", "пиздёнка",
    "пиздёночка", "пиздёныш", "пиздёнышка", "пиздень", "пиздеть", 
    "пиздеть — не кули ворочать, — спина не болит", "пиздеться", "пиздец",
    "пиздец подкрался незаметно", "пиздецки", "пиздецкий", "пиздецовый",
    "пиздёшечка", "пиздёшка", "пизди, пизди: приятно слушать", "пиздий",
    "пиздиловка", "пиздить", "пиздиться", "пиздишка", "пиздища", "пиздище",
    "пиздливый", "пиздлявый", "пиздлявый ящик", "пиздня", "пиздоблядство",
    "пиздобол", "пиздоболить", "пиздобольство", "пиздобратия", "пиздовать",
    "пиздоглазый", "пиздоделие", "пиздодельный", "пиздоёбство", "пиздой мух ловить",
    "пиздой накрыться", "пиздоквак", "пиздолиз", "пиздолизка", "пиздомудство",
    "пиздопроёбище", "пиздопротивный", "пиздорванец", "пиздорванец хуев",
    "пиздорванка", "пиздорез", "пиздоремонтник", "пиздоремонтничек", "пиздос",
    "пиздосий", "пиздострадалец", "пиздохаться", "пиздоход", "пиздохранилище",
    "пиздошить", "пизду в лапти обувать", "пиздуй", "пиздун", "пиздуна запускать",
    "пиздуна запустить", "пиздушечка", "пиздушка", "пизды дать", "пиздык",
    "пиздюк", "пиздюлей вложить", "пиздюлей навешать", "пиздюлей навставлять",
    "пиздюлей отхватить", "пиздюлина", "пиздюль", "пиздюря", "пиздюхать",
    "пиздюшка", "пиздякнуться", "пиздянка", "пиздятина", "пиздятинка", "пиздячить",
    "пиздящий", "пизже", "пизженый", "пинать хуи", "пинать хуй", "по ебалу получить",
    "по пизде мешалкой", "по пизде мешалкой словить", "по хую", "повъёбывать",
    "повыёбываться", "под ногти выебать", "подарок — из пизды огарок", "подзаебать",
    "подзаебаться", "подзаебти", "подохуевший", "подохуеть", "подпизживать",
    "подхуек", "подъёб", "подъебать", "подъебаться", "подъебаш", "Подъебишкин",
    "подъёбка", "подъебнуть", "подъебон", "подъебончик", "подъебушка", "подъёбщик",
    "подъёбывать", "Подъебышкин", "поебатор", "поебать", "поёбать", "поебаться",
    "поебень", "поёбка", "поебок", "поебота", "поеботина", "поебстись", "поебти",
    "поебтись", "поебусенка", "поебуха", "поебушечка", "поебушка", "поёбывать",
    "пойти по пизде", "показать хуёв тачку", "показать хуй", "показать хуй огромный",
    "полный похуист", "положить хуй", "полпизды", "получить крупный хуй",
    "получить от хуя уши", "получить пизды", "получить хуй", "полхуя",
    "понеслась пизда по кочкам", "понтоёб", "понтоёбский", "поперехуярить",
    "поперехуячить", "попизделки", "попиздеть", "попиздистее", "попиздить",
    "попиздиться", "попиздовать", "попизже", "послать в пизду",
    "последний хуй без соли доедать", "посылать в пизду", "потреблядство", "пох",
    "похуизм", "похуист", "похуистка", "похуй", "похуй пидору чулки", "похую",
    "похуястее", "похуястей", "пошароёбиться", "пошли на хуй", "приебаться",
    "приёбываться", "прикидывать хуй к носу", "прикинуть хуй к носу",
    "прикрыть ебушатник", "припиздень", "припиздеть", "припиздить", "припиздок",
    "припиздюхать", "прихуеть", "прихуяривать", "прихуярить", "про пизду ни слова",
    "проблядь", "проёб", "проебав", "проёбанный", "проебать", "проебаться",
    "проебланить", "проебти", "проёбчик", "проёбщик", "проёбщица", "проёбывать",
    "проёбываться", "пропиздеть", "пропиздеться", "пропиздон",
    "проскакивать между ёбаных", "проскочить между ёбаных", "протягивать пизду",
    "прыгнуть на хуй", "пятикрылый шестихуй", "рад дурак, что хуй велик",
    "раздавать смехуёчки", "раззуделася пизда", "разъёб", "разъёба", "разъебай",
    "разъебайский", "разъебалово", "разъебать", "разъебон", "разъебончик",
    "разъебти", "разъебуха", "разъёбывать", "раскурочить ебало", "распидорасить",
    "распиздеть", "распиздеться", "распиздун", "распиздяй", "распиздяйка",
    "распиздяйский", "распиздяйство", "распроебать", "расхлестать ебосос",
    "расхуюжить", "расхуяривать", "расхуяриваться", "расхуярить", "расхуяриться",
    "расхуячить", "руки под хуй заточены", "с какого хуя", "с нихуя",
    "с пиздий волос", "с хуёчка капает", "с хуя ли", "с хуя ль", "свиноёб",
    "свистни в хуй", "сдуру можно и хуй сломать", "семихуй", "Скороёбишка",
    "слово за слово, хуем по столу", "слушать пиздой", "смехуёчки",
    "смехуёчки раздавать", "смешить пизду", "смешно дураку, что хуй на боку",
    "смотреть как пизда на лимон", "собственными ёбалдами подавишься",
    "сосать хуй", "соси хуй утопленника!", "соси хуй!", "социоблядь",
    "спиздануть", "спиздеть", "спиздивший", "спиздить", "спиздиться", "спизженный",
    "сравнить хуй с пальцем", "старая пизда", "старый хуй", "сто хуёв — большая куча?",
    "страхоёбина", "страхопиздище", "сунуть в еблецо", "схуячить", "сцуко",
    "съебаторы", "съебаторы врубить", "съебать", "съебаться", "съебошить",
    "съёбывать", "съёбываться", "таких друзей — за хуй да в музей",
    "таракану хуй приделать", "то ли лыжи не едут, то ли я ебанутый", "толстопиздый",
    "торговать пиздой", "торговать пиздой и жопой", "тупая пизда", "тупиздень",
    "тупопёздный", "ты что, хуем подавился?", "угощать пиздой", "уёба", "уебан",
    "уёбан", "уебанский", "уебать", "уебаться", "уёбище", "уёбищность",
    "уёбищный", "уёбок", "уёбский", "уёбство", "уебти", "уёбывать", "уёбыш",
    "упиздить", "упиздовать", "ухуякивать", "ухуярить", "хитровыебанность",
    "хитровыебанный", "хоть бы хуй", "хоть самого в жопу сиськой еби",
    "хрен моржовый", "худоёбина", "хуё-моё", "хуев", "хуёв тачку и дров водокачку",
    "хуева туча", "хуевастый", "хуевато", "хуеватый", "хуёвее", "хуёвей",
    "хуёвенький", "хуевертить", "хуёвина", "хуёвина с морковиной", "хуёвинка", "хуёвить",
    "хуёвничать", "хуёво", "хуёвость", "хуевый", "хуёвый", "хуеглот",
    "хуеглотина", "хуежоп", "хуежопость", "хуежопый", "хуёк",
    "хуем груши выколачивать", "хуем груши околачивать", "хуем груши сбивать",
    "хуем задеть", "хуем запугать", "хуем наградить", "хуем разворочена",
    "хуем толкнуть", "хуем угостить", "хуем угощать", "хуем умыть", "хуемразь",
    "хуеносец", "хуеньки", "хуепас", "хуеплёт", "хуеплётка", "хуепутало",
    "хуерга", "хуерговина", "хуерыга", "хуерык", "хуерылый", "хуесос",
    "хуесос ёбаный", "хуесосина", "хуесосинг", "хуесосить", "хуесоска",
    "хуета", "хуета на хуете", "хуетень", "хуетища", "хуеть", "хуец",
    "хуёчек", "хуёчек плачет жгучею слезой", "хуи", "хуи гну", "хуи жевать",
    "хуи пинать", "хуила", "хуилище", "хуило", "хуило моржовый", "хуильник",
    "хуина", "хуинушка", "хуистый", "хуишечко", "хуишко", "хуище", "хуй",
    "хуй без соли доедать", "хуй в кожаном пальто", "хуй в пальто",
    "хуй важный", "хуй вставить по яички", "хуй гну", "хуй да ни хуя",
    "хуй до дома доволочь", "хуй его знает", "хуй забить", "хуй знает",
    "хуй колом", "хуй ли", "хуй моржовый", "хуй на блюде", "хуй на колёсиках",
    "хуй на ны", "хуй на рыло", "хуй на рыло, чтоб сердце не ныло", "хуй наны",
    "хуй не стоит", "хуй ночевал", "хуй один", "хуй по всей морде",
    "хуй показать", "хуй проссышь", "хуй с горы", "хуй с горы — большая скорость?",
    "хуй с горы — какая скорость?", "хуй с тобой", "хуй сосали комбайнёры",
    "хуй сосать", "хуй там", "хуй тебе", "хуй тебе в рыло",
    "хуй тебе на воротник", "хуй тебе на рыло", "хуй трёхколёсный",
    "хуй ушастый", "хуй царапать", "хуй-перехуй", "Хуйкино", "хуйлан", "хуйло",
    "хуйлыга", "хуйнуть", "хуйню спороть", "хуйня", "хуйня на постном масле",
    "хуйство", "хуле", "хули", "хулиард", "хуль", "хуля", "хуля-перехуля",
    "хуюжить", "хуючить", "хуюшки", "хуя с два", "хуяк", "хуяка", "хуякать",
    "хуякнуть", "хуякнуться", "хуякс", "хуями обложить", "хуяра", "хуярить",
    "хуяриться", "хуястый", "хуячить", "хуяшить",
    "через три пизды колено", "через хуй зари не видит", "через хуй кинуть",
    "чешется пиздища", "чешется пиздище", "что за ёб твою мать?",
    "шароёбить", "шароёбиться", "шароёбство",
    "шахтёрам — кресты, инженерам — пизды, директору — нары, владельцу — Канары",
    "это у вас в пизде квас, а у нас — в бочках",
    "ябать", "ябти", "ябтись"}

# Game/inline reklama kalit so'zlar/domenlar
SUSPECT_KEYWORDS = {"open game", "play", "играть", "открыть игру", "game", "cattea", "gamee", "hamster", "notcoin", "tap to earn", "earn", "clicker"}
SUSPECT_DOMAINS = {"cattea", "gamee", "hamster", "notcoin", "tgme", "t.me/gamee", "textra.fun", "ton"}

# ----------- DM Broadcast (Owner only) -----------
SUB_USERS_FILE = "subs_users.json"

OWNER_IDS = {165553982}

def is_owner(update: Update) -> bool:
    u = update.effective_user
    return bool(u and u.id in OWNER_IDS)

# Postgres connection pool
DB_POOL: Optional["asyncpg.Pool"] = None

def _get_db_url() -> Optional[str]:
    return (
        os.getenv("DATABASE_URL")
        or os.getenv("INTERNAL_DATABASE_URL")
        or os.getenv("DATABASE_INTERNAL_URL")
        or os.getenv("DB_URL")
    )


async def init_db(app=None):
    """Create asyncpg pool and ensure tables exist. Also migrate JSON -> DB once."""
    global DB_POOL
    db_url = _get_db_url()
    if not db_url:
        log.warning("DATABASE_URL topilmadi; DM ro'yxati JSON faylga yoziladi (ephemeral).")
        return
    if asyncpg is None:
        log.error("asyncpg o'rnatilmagan. requirements.txt ga 'asyncpg' qo'shing.")
        return

    # PaaS (Render/Railway) Postgres ko'pincha SSL talab qiladi.
    ssl_ctx = ssl.create_default_context()

    # Ba'zan `postgres://` bo'ladi; moslik uchun sxemani normalizatsiya qilamiz.
    if db_url.startswith("postgres://"):
        db_url = "postgresql://" + db_url[len("postgres://"):]

    # asyncpg SSL'ni `ssl=` orqali boshqaradi; dsn ichidagi sslmode parametrlari ba'zan muammo qiladi.
    try:
        u = urlparse(db_url)
        qs = dict(parse_qsl(u.query, keep_blank_values=True))
        for k in list(qs.keys()):
            if k.lower() in ("sslmode", "sslrootcert", "sslcert", "sslkey"):
                qs.pop(k, None)
        db_url = urlunparse(u._replace(query=urlencode(qs)))
    except Exception:
        pass

    # Retry/backoff bilan pool ochamiz (Render free kabi DB'larda foydali).
    DB_POOL = None
    for attempt in range(1, 6):
        try:
            host = (urlparse(db_url).hostname or "")
            # Railway internal hostlarda SSL kerak bo'lmasligi mumkin
            use_ssl = False if host.endswith(".railway.internal") else ssl_ctx
            DB_POOL = await asyncpg.create_pool(
                dsn=db_url,
                min_size=1,
                max_size=5,
                ssl=use_ssl,
                timeout=30,
                max_inactive_connection_lifetime=300,
            )
            log.info("Postgres DB_POOL ochildi (attempt=%s).", attempt)
            break
        except Exception as e:
            log.warning("Postgres ulanish xatosi (attempt=%s/5): %r", attempt, e)
            await asyncio.sleep(min(2 ** (attempt - 1), 16))

    if DB_POOL is None:
        log.error("Postgres'ga ulanib bo'lmadi. DB funksiyalar vaqtincha o'chadi; bot ishlashda davom etadi.")
        return

    async with DB_POOL.acquire() as con:
        await con.execute(
            """
            CREATE TABLE IF NOT EXISTS dm_users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                is_bot BOOLEAN DEFAULT FALSE,
                language_code TEXT,
                last_seen TIMESTAMPTZ DEFAULT now()
            );
            """
        )

    # Ensure per-group tables exist
    try:
        await init_group_db()
    except Exception as e:
        log.warning("init_group_db xatolik: %r", e)

    # Migrate from JSON (best-effort, only if DB empty)
    try:
        if DB_POOL:
            async with DB_POOL.acquire() as con:
                count_row = await con.fetchval("SELECT COUNT(*) FROM dm_users;")
            if count_row == 0 and os.path.exists(SUB_USERS_FILE):
                s = _load_ids(SUB_USERS_FILE)
                if s:
                    async with DB_POOL.acquire() as con:
                        async with con.transaction():
                            for cid in s:
                                try:
                                    cid_int = int(cid)
                                except Exception:
                                    continue
                                await con.execute(
                                    "INSERT INTO dm_users (user_id) VALUES ($1) ON CONFLICT DO NOTHING;",
                                    cid_int
                                )
                    log.info(f"Migratsiya: JSON dan Postgresga {len(s)} ta ID import qilindi.")
    except Exception as e:
        log.warning("Migratsiya xatolik: %r", e)

async def dm_upsert_user(user):
    """Add/update a user to dm_users (Postgres if available, else JSON)."""
    global DB_POOL
    if user is None:
        return
    if DB_POOL:
        try:
            async with DB_POOL.acquire() as con:
                await con.execute(
                    """
                    INSERT INTO dm_users (user_id, username, first_name, last_name, is_bot, language_code, last_seen)
                    VALUES ($1,$2,$3,$4,$5,$6, now())
                    ON CONFLICT (user_id) DO UPDATE SET
                        username=EXCLUDED.username,
                        first_name=EXCLUDED.first_name,
                        last_name=EXCLUDED.last_name,
                        is_bot=EXCLUDED.is_bot,
                        language_code=EXCLUDED.language_code,
                        last_seen=now();
                    """,
                    user.id, user.username, user.first_name, user.last_name, user.is_bot, getattr(user, "language_code", None)
                )
        except Exception as e:
            log.warning(f"dm_upsert_user(DB) xatolik: {e}")
    else:
        # Fallback to JSON
        add_chat_to_subs_fallback(user)

async def dm_all_ids() -> List[int]:
    global DB_POOL
    if DB_POOL:
        try:
            async with DB_POOL.acquire() as con:
                rows = await con.fetch("SELECT user_id FROM dm_users;")
            return [r["user_id"] for r in rows]
        except Exception as e:
            log.warning(f"dm_all_ids(DB) xatolik: {e}")
            return []
    else:
        return list(_load_ids(SUB_USERS_FILE))



# ==================== PER-GROUP SETTINGS (DB-backed) ====================

# In-memory fallback (DB bo'lmasa ham multi-guruh ishlashi uchun)
_MEM_GROUP_SETTINGS: dict[int, dict] = {}
_MEM_GROUP_COUNTS: dict[tuple[int, int], int] = {}
_MEM_GROUP_PRIVS: set[tuple[int, int]] = set()
_MEM_GROUP_BLOCKS: dict[tuple[int, int], datetime] = {}

_GROUP_SETTINGS_CACHE: dict[int, dict] = {}
_GROUP_SETTINGS_CACHE_TS: dict[int, float] = {}
_GROUP_SETTINGS_TTL = 30.0  # seconds
_UNSET = object()

def _default_group_settings() -> dict:
    return {"tun": False, "kanal_username": None, "majbur_limit": 0}

async def init_group_db():
    """Create per-group tables (settings, counts, privileges, blocks)."""
    if not DB_POOL:
        return
    async with DB_POOL.acquire() as con:
        await con.execute(
            """
            CREATE TABLE IF NOT EXISTS group_settings (
                chat_id BIGINT PRIMARY KEY,
                tun BOOLEAN DEFAULT FALSE,
                kanal_username TEXT,
                majbur_limit INT DEFAULT 0,
                updated_at TIMESTAMPTZ DEFAULT now()
            );
            """
        )
        await con.execute(
            """
            CREATE TABLE IF NOT EXISTS group_user_counts (
                chat_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                cnt INT NOT NULL DEFAULT 0,
                updated_at TIMESTAMPTZ DEFAULT now(),
                PRIMARY KEY (chat_id, user_id)
            );
            """
        )
        await con.execute(
            """
            CREATE TABLE IF NOT EXISTS group_privileges (
                chat_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                granted_at TIMESTAMPTZ DEFAULT now(),
                PRIMARY KEY (chat_id, user_id)
            );
            """
        )
        await con.execute(
            """
            CREATE TABLE IF NOT EXISTS group_blocks (
                chat_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                until_ts TIMESTAMPTZ,
                updated_at TIMESTAMPTZ DEFAULT now(),
                PRIMARY KEY (chat_id, user_id)
            );
            """
        )

async def get_group_settings(chat_id: int) -> dict:
    """Return settings for a group (cached)."""
    # cache
    try:
        import time
        now = time.time()
        if chat_id in _GROUP_SETTINGS_CACHE and (now - _GROUP_SETTINGS_CACHE_TS.get(chat_id, 0)) < _GROUP_SETTINGS_TTL:
            return dict(_GROUP_SETTINGS_CACHE[chat_id])
    except Exception:
        pass

    if not DB_POOL:
        s = dict(_MEM_GROUP_SETTINGS.get(chat_id) or _default_group_settings())
        _GROUP_SETTINGS_CACHE[chat_id] = dict(s)
        _GROUP_SETTINGS_CACHE_TS[chat_id] = __import__("time").time()
        return s

    try:
        async with DB_POOL.acquire() as con:
            row = await con.fetchrow(
                "SELECT tun, kanal_username, majbur_limit FROM group_settings WHERE chat_id=$1;",
                chat_id
            )
        if row:
            s = {"tun": bool(row["tun"]), "kanal_username": row["kanal_username"], "majbur_limit": int(row["majbur_limit"] or 0)}
        else:
            s = _default_group_settings()
        _GROUP_SETTINGS_CACHE[chat_id] = dict(s)
        _GROUP_SETTINGS_CACHE_TS[chat_id] = __import__("time").time()
        return s
    except Exception as e:
        log.warning("get_group_settings(DB) xatolik: %r", e)
        s = dict(_MEM_GROUP_SETTINGS.get(chat_id) or _default_group_settings())
        return s

async def set_group_settings(chat_id: int, *, tun=_UNSET, kanal_username=_UNSET, majbur_limit=_UNSET):
    """Upsert group settings; only provided fields are updated."""
    # in-memory always updated (fallback)
    s = dict(_MEM_GROUP_SETTINGS.get(chat_id) or _default_group_settings())
    if tun is not _UNSET:
        s["tun"] = bool(tun)
    if kanal_username is not _UNSET:
        s["kanal_username"] = kanal_username
    if majbur_limit is not _UNSET:
        s["majbur_limit"] = int(majbur_limit or 0)
    _MEM_GROUP_SETTINGS[chat_id] = s

    _GROUP_SETTINGS_CACHE[chat_id] = dict(s)
    try:
        _GROUP_SETTINGS_CACHE_TS[chat_id] = __import__("time").time()
    except Exception:
        pass

    if not DB_POOL:
        return
    try:
        # build dynamic update
        cols = []
        vals = []
        if tun is not _UNSET:
            cols.append("tun")
            vals.append(bool(tun))
        if kanal_username is not _UNSET:
            cols.append("kanal_username")
            vals.append(kanal_username)
        if majbur_limit is not _UNSET:
            cols.append("majbur_limit")
            vals.append(int(majbur_limit or 0))
        # if nothing to update, just ensure row exists
        async with DB_POOL.acquire() as con:
            if not cols:
                await con.execute(
                    "INSERT INTO group_settings (chat_id) VALUES ($1) ON CONFLICT (chat_id) DO NOTHING;",
                    chat_id
                )
                return
            # Insert with full values using COALESCE from existing when not passed
            # Easier: upsert with defaults but update only provided cols.
            set_sql = ", ".join([f"{c}=EXCLUDED.{c}" for c in cols] + ["updated_at=now()"])
            # Provide all columns in insert so excluded has them.
            await con.execute(
                f"""
                INSERT INTO group_settings (chat_id, tun, kanal_username, majbur_limit)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (chat_id) DO UPDATE SET {set_sql};
                """,
                chat_id,
                bool(s.get("tun")),
                s.get("kanal_username"),
                int(s.get("majbur_limit") or 0),
            )
    except Exception as e:
        log.warning("set_group_settings(DB) xatolik: %r", e)

async def get_user_count_db(chat_id: int, user_id: int) -> int:
    if not DB_POOL:
        return int(_MEM_GROUP_COUNTS.get((chat_id, user_id), 0))
    try:
        async with DB_POOL.acquire() as con:
            v = await con.fetchval(
                "SELECT cnt FROM group_user_counts WHERE chat_id=$1 AND user_id=$2;",
                chat_id, user_id
            )
        return int(v or 0)
    except Exception as e:
        log.warning("get_user_count_db xatolik: %r", e)
        return int(_MEM_GROUP_COUNTS.get((chat_id, user_id), 0))

async def inc_user_count_db(chat_id: int, user_id: int, delta: int = 1):
    if delta == 0:
        return
    key = (chat_id, user_id)
    _MEM_GROUP_COUNTS[key] = int(_MEM_GROUP_COUNTS.get(key, 0)) + int(delta)
    if not DB_POOL:
        return
    try:
        async with DB_POOL.acquire() as con:
            await con.execute(
                """
                INSERT INTO group_user_counts (chat_id, user_id, cnt)
                VALUES ($1,$2,$3)
                ON CONFLICT (chat_id, user_id) DO UPDATE SET
                    cnt = group_user_counts.cnt + EXCLUDED.cnt,
                    updated_at = now();
                """,
                chat_id, user_id, int(delta)
            )
    except Exception as e:
        log.warning("inc_user_count_db xatolik: %r", e)

async def top_group_counts_db(chat_id: int, limit: int = 100) -> List[tuple[int, int]]:
    if not DB_POOL:
        items = [((cid, uid), cnt) for (cid, uid), cnt in _MEM_GROUP_COUNTS.items() if cid == chat_id]
        items.sort(key=lambda x: x[1], reverse=True)
        return [(uid, cnt) for ((_, uid), cnt) in items[:limit]]
    try:
        async with DB_POOL.acquire() as con:
            rows = await con.fetch(
                "SELECT user_id, cnt FROM group_user_counts WHERE chat_id=$1 ORDER BY cnt DESC LIMIT $2;",
                chat_id, int(limit)
            )
        return [(int(r["user_id"]), int(r["cnt"])) for r in rows]
    except Exception as e:
        log.warning("top_group_counts_db xatolik: %r", e)
        items = [((cid, uid), cnt) for (cid, uid), cnt in _MEM_GROUP_COUNTS.items() if cid == chat_id]
        items.sort(key=lambda x: x[1], reverse=True)
        return [(uid, cnt) for ((_, uid), cnt) in items[:limit]]

async def clear_group_counts_db(chat_id: int):
    # memory
    for k in list(_MEM_GROUP_COUNTS.keys()):
        if k[0] == chat_id:
            _MEM_GROUP_COUNTS.pop(k, None)
    if not DB_POOL:
        return
    try:
        async with DB_POOL.acquire() as con:
            await con.execute("DELETE FROM group_user_counts WHERE chat_id=$1;", chat_id)
    except Exception as e:
        log.warning("clear_group_counts_db xatolik: %r", e)

async def grant_priv_db(chat_id: int, user_id: int):
    _MEM_GROUP_PRIVS.add((chat_id, user_id))
    if not DB_POOL:
        return
    try:
        async with DB_POOL.acquire() as con:
            await con.execute(
                "INSERT INTO group_privileges (chat_id, user_id) VALUES ($1,$2) ON CONFLICT DO NOTHING;",
                chat_id, user_id
            )
    except Exception as e:
        log.warning("grant_priv_db xatolik: %r", e)

async def group_has_priv(chat_id: int, user_id: int) -> bool:
    if (chat_id, user_id) in _MEM_GROUP_PRIVS:
        return True
    if not DB_POOL:
        return False
    try:
        async with DB_POOL.acquire() as con:
            v = await con.fetchval(
                "SELECT 1 FROM group_privileges WHERE chat_id=$1 AND user_id=$2;",
                chat_id, user_id
            )
        return bool(v)
    except Exception as e:
        log.warning("group_has_priv xatolik: %r", e)
        return False

async def clear_privs_db(chat_id: int):
    _MEM_GROUP_PRIVS.difference_update({k for k in _MEM_GROUP_PRIVS if k[0] == chat_id})
    if not DB_POOL:
        return
    try:
        async with DB_POOL.acquire() as con:
            await con.execute("DELETE FROM group_privileges WHERE chat_id=$1;", chat_id)
    except Exception as e:
        log.warning("clear_privs_db xatolik: %r", e)

async def set_block_until_db(chat_id: int, user_id: int, until_ts: datetime):
    _MEM_GROUP_BLOCKS[(chat_id, user_id)] = until_ts
    if not DB_POOL:
        return
    try:
        async with DB_POOL.acquire() as con:
            await con.execute(
                """
                INSERT INTO group_blocks (chat_id, user_id, until_ts)
                VALUES ($1,$2,$3)
                ON CONFLICT (chat_id, user_id) DO UPDATE SET
                    until_ts=EXCLUDED.until_ts,
                    updated_at=now();
                """,
                chat_id, user_id, until_ts
            )
    except Exception as e:
        log.warning("set_block_until_db xatolik: %r", e)

async def get_block_until_db(chat_id: int, user_id: int) -> Optional[datetime]:
    if (chat_id, user_id) in _MEM_GROUP_BLOCKS:
        return _MEM_GROUP_BLOCKS.get((chat_id, user_id))
    if not DB_POOL:
        return None
    try:
        async with DB_POOL.acquire() as con:
            v = await con.fetchval(
                "SELECT until_ts FROM group_blocks WHERE chat_id=$1 AND user_id=$2;",
                chat_id, user_id
            )
        if v:
            _MEM_GROUP_BLOCKS[(chat_id, user_id)] = v
        return v
    except Exception as e:
        log.warning("get_block_until_db xatolik: %r", e)
        return _MEM_GROUP_BLOCKS.get((chat_id, user_id))

async def clear_block_db(chat_id: int, user_id: int):
    _MEM_GROUP_BLOCKS.pop((chat_id, user_id), None)
    if not DB_POOL:
        return
    try:
        async with DB_POOL.acquire() as con:
            await con.execute("DELETE FROM group_blocks WHERE chat_id=$1 AND user_id=$2;", chat_id, user_id)
    except Exception as e:
        log.warning("clear_block_db xatolik: %r", e)

def _parse_kanal_usernames(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    s = str(raw).strip()
    if not s:
        return []
    # stored as JSON list
    if s.startswith("["):
        try:
            data = json.loads(s)
            if isinstance(data, list):
                out = []
                for x in data:
                    if not x:
                        continue
                    t = str(x).strip()
                    if not t:
                        continue
                    if not t.startswith("@"):
                        t = "@" + t.lstrip("@")
                    out.append(t)
                return out
        except Exception:
            pass
    # fallback: split by spaces
    parts = [p for p in re.split(r"[\s,]+", s) if p]
    out = []
    for p in parts:
        t = p.strip()
        if not t:
            continue
        if not t.startswith("@"):
            t = "@" + t.lstrip("@")
        out.append(t)
    # unique preserve order
    seen=set()
    res=[]
    for t in out:
        if t.lower() in seen:
            continue
        seen.add(t.lower())
        res.append(t)
    return res

async def _check_all_channels(user_id: int, bot, kanal_list: List[str]) -> tuple[bool, List[str]]:
    missing = []
    for ch in kanal_list:
        try:
            m = await bot.get_chat_member(ch, user_id)
            if m.status not in ("member", "administrator", "creator"):
                missing.append(ch)
        except Exception:
            missing.append(ch)
    return (len(missing) == 0, missing)

# Mention helpers (HTML)
def _user_label_from_user(u) -> str:
    if getattr(u, "username", None):
        return "@" + u.username
    name = (getattr(u, "full_name", None) or "").strip()
    if not name:
        name = (getattr(u, "first_name", None) or "").strip()
    return name or str(u.id)

def _mention_userid_html(user_id: int, label: str) -> str:
    return f'<a href="tg://user?id={user_id}">{html.escape(str(label))}</a>'

async def _mention_from_id(bot, chat_id: int, user_id: int, cache: dict[int, str]) -> str:
    if user_id in cache:
        return cache[user_id]
    label = str(user_id)
    try:
        cm = await bot.get_chat_member(chat_id, user_id)
        u = getattr(cm, "user", None)
        if u:
            label = _user_label_from_user(u)
    except Exception:
        pass
    mention = _mention_userid_html(user_id, label)
    cache[user_id] = mention
    return mention

# ==================== END PER-GROUP SETTINGS (DB-backed) ====================



async def dm_remove_user(user_id: int):
    global DB_POOL
    if DB_POOL:
        try:
            async with DB_POOL.acquire() as con:
                await con.execute("DELETE FROM dm_users WHERE user_id=$1;", user_id)
        except Exception as e:
            log.warning(f"dm_remove_user(DB) xatolik: {e}")
    else:
        remove_chat_from_subs_fallback(user_id)

# ----------- Fallback JSON helpers (only used if DB not available) -----------
def _load_ids(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()

def _save_ids(path: str, data: set):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sorted(list(data)), f, ensure_ascii=False, indent=2)
    except Exception as e:
        try:
            log.warning(f"IDs saqlashda xatolik: {e}")
        except Exception:
            print(f"IDs saqlashda xatolik: {e}")

def add_chat_to_subs_fallback(user_or_chat):
    s = _load_ids(SUB_USERS_FILE)
    # user_or_chat is User in our call sites
    cid = getattr(user_or_chat, "id", None)
    if cid is not None:
        s.add(cid)
        _save_ids(SUB_USERS_FILE, s)
    return "user"

def remove_chat_from_subs_fallback(user_id: int):
    s = _load_ids(SUB_USERS_FILE)
    if user_id in s:
        s.remove(user_id)
        _save_ids(SUB_USERS_FILE, s)
    return "user"


# ----------- Privilege/Admin helpers -----------
async def is_admin(update: Update) -> bool:
    chat = update.effective_chat
    msg = update.effective_message
    user = update.effective_user
    if not chat:
        return False
    try:
        # Anonymous admin (message on behalf of the group itself)
        if msg and getattr(msg, "sender_chat", None):
            sc = msg.sender_chat
            if sc.id == chat.id:
                return True
            # Linked channel posting into a supergroup
            linked_id = getattr(chat, "linked_chat_id", None)
            if linked_id and sc.id == linked_id:
                return True
        # Regular user-based admin check
        if user:
            member = await update.get_bot().get_chat_member(chat.id, user.id)
            return member.status in ("administrator", "creator", "owner")
        return False
    except Exception as e:
        log.warning(f"is_admin tekshiruvda xatolik: {e}")
        return False

async def is_privileged_message(msg, bot) -> bool:
    """Adminlar, creatorlar yoki guruh/linked kanal nomidan yozilgan (sender_chat) xabarlar uchun True."""
    try:
        chat = msg.chat
        user = msg.from_user
        # Anonymous admin (group) yoki linked kanal
        if getattr(msg, "sender_chat", None):
            sc = msg.sender_chat
            if sc.id == chat.id:
                return True
            linked_id = getattr(chat, "linked_chat_id", None)
            if linked_id and sc.id == linked_id:
                return True
        # Odatdagi admin/creator
        if user:
            member = await bot.get_chat_member(chat.id, user.id)
            if member.status in ("administrator", "creator", "owner"):
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

def admin_add_link(bot_username: str) -> str:
    rights = [
        'delete_messages','restrict_members','invite_users',
        'pin_messages','manage_topics','manage_video_chats','manage_chat'
    ]
    rights_param = '+'.join(rights)
    return f"https://t.me/{bot_username}?startgroup&admin={rights_param}"

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
    # /start bosgan foydalanuvchini DBga yozamiz (faqat private)
    try:
        if update.effective_chat.type == "private":
            await dm_upsert_user(update.effective_user)
    except Exception as e:
        log.warning(f"/start dm_upsert_user xatolik: {e}")

    kb = [[InlineKeyboardButton("➕ Добавить в группу", url=admin_add_link(context.bot.username))]]
    await update.effective_message.reply_text(
        "<b>ПРИВЕТ👋</b>\n\n"
        "Я удаляю из групп любые рекламные посты, ссылки, сообщения о <b>входе/выходе</b> и рекламу от вспомогательных ботов.\n\n"
        "Могу определить ваш <b>ID</b> профиля.\n\n"
        "Сделаю обязательным добавление людей в группу и подписку на канал (иначе писать нельзя) ➕\n\n"
        "Удаляю 18+ и нецензурную лексику, а делаю многое другое 👮‍♂️\n\n"
        "Справка по командам — /help\n\n"
        "Сам бот <b>не отправляет</b> никаких рекламных объявлений или ссылок 🚫\n\n"
        "Чтобы я работал, добавьте меня в группу и дайте <b>ПРАВА АДМИНА</b> 🙂\n\n"
        "Для связи и вопросов — @Devona0107\n\n"
        "Подпишитесь на наш канал: <b>@SOAuz</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb),
        disable_web_page_preview=True,
    )

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📌 <b>СПИСОК КОМАНД</b>\n\n"
"🔹 <b>/id</b> — Показать ваш ID.\n\n"
        "📘<b>ПОЛЕЗНЫЕ КОМАНДЫ</b>\n"
"🔹 <b>/night</b> — Ночной режим (все новые сообщения обычных пользователей будут автоматически удаляться).\n"
"🔹 <b>/nightoff</b> — Выключить ночной режим.\n"
"🔹 <b>/permit</b> — Выдать привилегию по reply.\n\n"
        "👥<b>ПРИНУДИТЕЛЬНОЕ ДОБАВЛЕНИЕ ЛЮДЕЙ В ГРУППЫ И КАНАЛЫ</b>\n"
"🔹 <b>/channel @username</b> — Включить обязательную подписку на указанный канал.\n"
"🔹 <b>/channeloff</b> — Отключить обязательную подписку.\n"
"🔹 <b>/forced [3–25]</b> — Включить обязательное добавление людей в группу.\n"
"🔹 <b>/forcedoff</b> — Отключить обязательное добавление.\n\n"
        "📈<b>ПОДСЧЁТ ЛЮДЕЙ, КОТОРЫЕ ДОБАВИЛИ</b>\n"
"🔹 <b>/top</b> — Топ участников по добавлениям.\n"
"🔹 <b>/cleangroup</b> — Обнулить счётчики всех пользователей.\n"
"🔹 <b>/count</b> — Сколько людей добавили вы.\n"
"🔹 <b>/replycount</b> — По reply: сколько добавил указанный пользователь.\n"
"🔹 <b>/cleanuser</b> — По reply: обнулить счётчик пользователя.\n")
    await update.effective_message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)

async def id_berish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    user = update.effective_user
    await update.effective_message.reply_text(f"🆔 {user.first_name}, ваш Telegram ID: {user.id}")

async def tun(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Только для администраторов.")
    chat_id = update.effective_chat.id
    await set_group_settings(chat_id, tun=True)
    await update.effective_message.reply_text("🌙 Ночной режим включен. Сообщения пользователей будут удалены.")


async def tunoff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Только для администраторов.")
    chat_id = update.effective_chat.id
    await set_group_settings(chat_id, tun=False)
    await update.effective_message.reply_text("🌞 Ночной режим выключен.")


async def ruxsat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Только для администраторов.")
    msg = update.effective_message
    if not msg.reply_to_message:
        return await msg.reply_text("Пожалуйста, ОТВЕТЬте на сообщение пользователя.")
    chat_id = update.effective_chat.id
    uid = msg.reply_to_message.from_user.id
    await grant_priv_db(chat_id, uid)
    # agar bloklangan bo'lsa, blokdan chiqaramiz
    try:
        await clear_block_db(chat_id, uid)
        await context.bot.restrict_chat_member(chat_id=chat_id, user_id=uid, permissions=FULL_PERMS)
    except Exception:
        pass
    await msg.reply_text(f"✅ <code>{uid}</code> Пользователю разрешено.", parse_mode="HTML")


async def kanal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Только для администраторов.")
    chat_id = update.effective_chat.id
    if context.args:
        chans = []
        for a in context.args:
            a = (a or "").strip()
            if not a:
                continue
            if not a.startswith("@"):
                a = "@" + a.lstrip("@")
            chans.append(a)
        # unique preserve order
        seen=set()
        uniq=[]
        for c in chans:
            k=c.lower()
            if k in seen:
                continue
            seen.add(k)
            uniq.append(c)
        # store as JSON list for multi-channel support
        raw = json.dumps(uniq, ensure_ascii=False) if len(uniq) != 1 else uniq[0]
        await set_group_settings(chat_id, kanal_username=raw)
        display = " ".join(uniq) if uniq else ""
        await update.effective_message.reply_text(f"📢 Обязательный канал: {display}")
    else:
        await update.effective_message.reply_text("Образец: /Channel @username")


async def kanaloff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Только для администраторов.")
    chat_id = update.effective_chat.id
    await set_group_settings(chat_id, kanal_username=None)
    await update.effective_message.reply_text("🚫 Обязательное требование к каналу удалено.")


def majbur_klaviatura():
    rows = [[3, 5, 7, 10, 12], [15, 18, 20, 25, 30]]
    keyboard = [[InlineKeyboardButton(str(n), callback_data=f"set_limit:{n}") for n in row] for row in rows]
    keyboard.append([InlineKeyboardButton("❌ ОТМЕНИТЬ ❌", callback_data="set_limit:cancel")])
    return InlineKeyboardMarkup(keyboard)

async def majbur(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Только для администраторов.")
    chat_id = update.effective_chat.id
    if context.args:
        try:
            val = int(context.args[0])
            if not (3 <= val <= 30):
                raise ValueError
            await set_group_settings(chat_id, majbur_limit=val)
            await update.effective_message.reply_text(
                f"✅ Обязательный лимит добавления лиц: <b>{val}</b>",
                parse_mode="HTML"
            )
        except ValueError:
            await update.effective_message.reply_text(
                "❌ Недопустимое значение. Допустимый диапазон: <b>3–30</b>. Например: <code>/forced 10</code>",
                parse_mode="HTML"
            )
    else:
        await update.effective_message.reply_text(
            "👥 Сколько я могу устанавливать обязательные добавления в группу? 👇\n"
            "Нет необходимости добавлять — /forcedoff",
            reply_markup=majbur_klaviatura()
        )


async def on_set_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user = q.from_user
    chat = q.message.chat if q.message else None
    if not (user and chat):
        return await q.answer()
    # only admins
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status not in ("administrator", "creator"):
            return await q.answer("Только администраторы!", show_alert=True)
    except Exception:
        return await q.answer("Ошибка проверки администратора.", show_alert=True)

    await q.answer()

    data = q.data.split(":", 1)[1] if ":" in q.data else ""
    if data == "cancel":
        return await q.edit_message_text("❌ Отменено.")
    try:
        val = int(data)
        if not (3 <= val <= 30):
            raise ValueError
    except ValueError:
        return await q.edit_message_text("❌ Неверное значение.")

    await set_group_settings(chat.id, majbur_limit=val)
    await q.edit_message_text(f"✅ Обязательный лимит: <b>{val}</b>", parse_mode="HTML")


async def majburoff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Только для администраторов.")
    chat_id = update.effective_chat.id
    await set_group_settings(chat_id, majbur_limit=0)
    await update.effective_message.reply_text("🚫 Обязательное добавление лица было отключено..")


async def top_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Только для администраторов.")
    chat_id = update.effective_chat.id
    items = await top_group_counts_db(chat_id, limit=100)
    if not items:
        return await update.effective_message.reply_text("Пока никто не добавил людей.")
    lines = ["🏆 <b>ТОП 100 участников по добавлениям</b> (TOP 100):"]
    cache: dict[int, str] = {}
    for i, (uid, cnt) in enumerate(items, start=1):
        mention = await _mention_from_id(context.bot, chat_id, uid, cache)
        lines.append(f"{i}. {mention} — <b>{cnt}</b> ta")
    await update.effective_message.reply_text("\n".join(lines), parse_mode="HTML")


async def cleangroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Только для администраторов.")
    chat_id = update.effective_chat.id
    await clear_group_counts_db(chat_id)
    await clear_privs_db(chat_id)
    await update.effective_message.reply_text("🗑 Счёт и привилегии были сброшены на 0 для этой группы.")


async def count_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    uid = update.effective_user.id
    settings = await get_group_settings(chat_id)
    limit = int(settings.get("majbur_limit") or 0)
    cnt = await get_user_count_db(chat_id, uid)
    if limit > 0:
        qoldi = max(limit - cnt, 0)
        await update.effective_message.reply_text(f"📊 Вы {cnt} шт добавили людей. Осталось: {qoldi} шт.")
    else:
        await update.effective_message.reply_text(f"📊 Вы {cnt} шт добавили людей. (Принудительное добавление не активно)")


async def replycount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Только для администраторов.")
    msg = update.effective_message
    if not msg.reply_to_message:
        return await msg.reply_text("Пожалуйста, ответьте пользователю (reply), чтобы узнать его счёт.")
    chat_id = update.effective_chat.id
    uid = msg.reply_to_message.from_user.id
    cnt = await get_user_count_db(chat_id, uid)
    await msg.reply_text(f"📊 <code>{uid}</code> добавил: <b>{cnt}</b>", parse_mode="HTML")


async def cleanuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Только для администраторов.")
    msg = update.effective_message
    if not msg.reply_to_message:
        return await msg.reply_text("Пожалуйста, ответьте пользователю (reply), чтобы сбросить его счёт.")
    chat_id = update.effective_chat.id
    uid = msg.reply_to_message.from_user.id
    # set to 0 by deleting row; also remove priv
    try:
        if DB_POOL:
            async with DB_POOL.acquire() as con:
                await con.execute("DELETE FROM group_user_counts WHERE chat_id=$1 AND user_id=$2;", chat_id, uid)
                await con.execute("DELETE FROM group_privileges WHERE chat_id=$1 AND user_id=$2;", chat_id, uid)
        _MEM_GROUP_COUNTS.pop((chat_id, uid), None)
        _MEM_GROUP_PRIVS.discard((chat_id, uid))
    except Exception:
        pass
    await msg.reply_text(f"🗑 Сброшено: <code>{uid}</code>", parse_mode="HTML")


async def kanal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    data = (q.data or "")

    # owner check (if encoded)
    owner_id = None
    if ":" in data:
        try:
            owner_id = int(data.split(":", 1)[1])
        except Exception:
            owner_id = None
        if owner_id and owner_id != uid:
            return await q.answer("Эта кнопка не для вас!", show_alert=True)

    await q.answer()
    chat_id = q.message.chat.id if q.message else None
    if not chat_id:
        return

    settings = await get_group_settings(chat_id)
    kanal_list = _parse_kanal_usernames(settings.get("kanal_username"))

    if not kanal_list:
        # requirement disabled
        try:
            await context.bot.restrict_chat_member(chat_id=chat_id, user_id=uid, permissions=FULL_PERMS)
        except Exception:
            pass
        return await q.edit_message_text("✅ Требование к каналу отключено. Теперь вы можете писать в группе.")

    ok, _missing = await _check_all_channels(uid, context.bot, kanal_list)
    if ok:
        try:
            await context.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=uid,
                permissions=FULL_PERMS,
            )
        except Exception:
            pass
        return await q.edit_message_text("✅ Ваше членство подтверждено. Теперь вы можете публиковать сообщения в группе.")
    return await q.edit_message_text("❌ Вы еще не являетесь участником канала.")


async def on_check_added(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id

    # faqat ogohlantirish olgan egasi bosa oladi
    data = q.data or ""
    owner_id = None
    if ":" in data:
        try:
            owner_id = int(data.split(":", 1)[1])
        except ValueError:
            owner_id = None
        if owner_id and owner_id != uid:
            return await q.answer("Эта кнопка не для вас!", show_alert=True)

    chat_id = q.message.chat.id if q.message else None
    if not chat_id:
        return await q.answer()

    settings = await get_group_settings(chat_id)
    limit = int(settings.get("majbur_limit") or 0)
    cnt = await get_user_count_db(chat_id, uid)

    # Talab bajarilgan holat: to'liq ruxsat
    if await group_has_priv(chat_id, uid) or (limit > 0 and cnt >= limit):
        try:
            await context.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=uid,
                permissions=FULL_PERMS,
            )
        except Exception:
            pass
        await clear_block_db(chat_id, uid)
        return await q.edit_message_text("✅ Запрос выполнен! Теперь вы можете писать в группе.")

    # Yetarli emas holat: MODAL oynacha
    qoldi = max(limit - cnt, 0)
    return await q.answer(
        f"❗ Вы пока {cnt} шт добавили пользователейz и еще {qoldi} шт надо добавить пользователей",
        show_alert=True
    )


async def on_grant_priv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    chat = q.message.chat if q.message else None
    user = q.from_user
    if not (chat and user):
        return await q.answer()
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status not in ("administrator", "creator"):
            return await q.answer("Только администраторы могут предоставлять привилегии!", show_alert=True)
    except Exception:
        return await q.answer("Ошибка при проверке.", show_alert=True)
    await q.answer()
    try:
        target_id = int((q.data or "").split(":", 1)[1])
    except Exception:
        return await q.edit_message_text("❌ Неверная информация.")
    await grant_priv_db(chat.id, target_id)
    # Unblock if blocked
    try:
        await clear_block_db(chat.id, target_id)
        await context.bot.restrict_chat_member(chat_id=chat.id, user_id=target_id, permissions=FULL_PERMS)
    except Exception:
        pass
    await q.edit_message_text(f"🎟 <code>{target_id}</code> Пользователю предоставлена ​​привилегия. Теперь он может писать.", parse_mode="HTML")


# ----------- Filters -----------
async def reklama_va_soz_filtri(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    # 🔒 Linked kanalning avtomatik forward postlari — teginmaymiz
    try:
        if await is_linked_channel_autoforward(msg, context.bot):
            return
    except Exception:
        pass

    if not msg or not msg.chat or not msg.from_user:
        return

    # Admin/creator/guruh nomidan xabarlar — teginmaymiz
    if await is_privileged_message(msg, context.bot):
        return

    # Oq ro'yxat
    if msg.from_user.id in WHITELIST or (msg.from_user.username and msg.from_user.username in WHITELIST):
        return

    chat_id = msg.chat_id
    settings = await get_group_settings(chat_id)

    # Tun rejimi (faqat shu guruh uchun)
    if settings.get("tun"):
        try:
            await msg.delete()
        except Exception:
            pass
        return

    # Kanal a'zoligi (faqat shu guruh uchun)
    kanal_list = _parse_kanal_usernames(settings.get("kanal_username"))
    if kanal_list:
        ok, _missing = await _check_all_channels(msg.from_user.id, context.bot, kanal_list)
        if not ok:
            try:
                await msg.delete()
            except Exception:
                pass
            mention_html = _mention_userid_html(msg.from_user.id, _user_label_from_user(msg.from_user))
            display = " ".join(kanal_list)
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Я подписался", callback_data=f"kanal_azo:{msg.from_user.id}")
            ]])
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ {mention_html}, вы не подписаны на канал {display}!",
                parse_mode=ParseMode.HTML,
                reply_markup=kb
            )
            return

    # agar Bot bo'lsa: reklama/ssilka, til/username
    if msg.via_bot:
        try:
            await msg.delete()
        except Exception:
            pass
        try:
            await context.bot.send_message(
                chat_id=msg.chat_id,
                text="🚫 Reklama/ssilka: Bot orqali yuborilgan xabar o'chirildi."
            )
        except Exception:
            pass
        return

    # text / caption tekshiramiz
    text = msg.text or msg.caption or ""
    if not text:
        return

    # suspicious keywords
    low = text.lower()

    # Matndan o‘yin reklamasini aniqlash (keyin o‘chirib yuboramiz)
    if any(k in low for k in SUSPECT_KEYWORDS):
        try:
            await msg.delete()
        except Exception:
            pass
        return

    # URL detection + aggressive filter (including obfuscations)
    if contains_url_like(text):
        try:
            await msg.delete()
        except Exception:
            pass
        return

    # Profanity / banned words (word-boundary + contains)
    for w in BAD_WORDS:
        if w in low:
            try:
                await msg.delete()
            except Exception:
                pass
            return


async def on_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg:
        return
    adder = msg.from_user
    members = msg.new_chat_members or []
    if not adder:
        return
    chat_id = msg.chat_id
    add_count = 0
    for m in members:
        if adder.id != m.id:
            add_count += 1
    if add_count:
        await inc_user_count_db(chat_id, adder.id, add_count)
    try:
        await msg.delete()
    except Exception:
        pass



async def on_left_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg:
        return
    try:
        await msg.delete()
    except Exception:
        pass


async def majbur_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    # 🔒 Linked kanalning avtomatik forward postlari — teginmaymiz
    try:
        if await is_linked_channel_autoforward(msg, context.bot):
            return
    except Exception:
        pass

    if not msg or not msg.chat or not msg.from_user:
        return

    # Admin/creator/guruh nomidan xabarlar — teginmaymiz
    if await is_privileged_message(msg, context.bot):
        return

    # Oq ro'yxat
    if msg.from_user.id in WHITELIST or (msg.from_user.username and msg.from_user.username in WHITELIST):
        return

    chat_id = msg.chat_id
    settings = await get_group_settings(chat_id)
    limit = int(settings.get("majbur_limit") or 0)
    if limit <= 0:
        return

    uid = msg.from_user.id

    # Privileged user (ruxsat)
    if await group_has_priv(chat_id, uid):
        return

    # Agar hozir bloklangan bo'lsa (DB), yana o'chiramiz va qaytamiz
    now = datetime.now(timezone.utc)
    until_prev = await get_block_until_db(chat_id, uid)
    if until_prev and now < until_prev:
        try:
            await msg.delete()
        except Exception:
            pass
        return

    cnt = await get_user_count_db(chat_id, uid)
    if cnt >= limit:
        return

    # delete message
    try:
        await msg.delete()
    except Exception:
        pass

    qoldi = max(limit - cnt, 0)

    # 1 daqiqaga bloklash (har safar tekshirib qayta bloklaydi)
    until = now + timedelta(minutes=1)
    await set_block_until_db(chat_id, uid, until)

    try:
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=uid,
            permissions=BLOCK_PERMS,
            until_date=until
        )
    except Exception:
        pass

    kb = [[InlineKeyboardButton("✅ Я добавил людей", callback_data=f"check_added:{uid}")],
          [InlineKeyboardButton("🎟 Выдать привилегию", callback_data=f"grant:{uid}")],
          [InlineKeyboardButton("👥 Добавить людей", url="https://t.me/share/url?url=Добавьтесь%20в%20нашу%20группу")]]
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"⚠️ Для публикации в группе нужно добавить {limit} человека! Осталось: {qoldi}.\n"
             f"⏳ заблокирован на минуту 1.\n\n"
             "✅ Добавьте людей и нажмите кнопку ниже:",
        reply_markup=InlineKeyboardMarkup(kb)
    )


async def on_my_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        st = update.my_chat_member.new_chat_member.status
    except Exception:
        return
    if st in (ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED):
        me = await context.bot.get_me()
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(
            '🔐 Botni admin qilish', url=admin_add_link(me.username)
        )]])
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=(
                    '⚠️ Bot hozircha *admin emas*.\n'
                    "Iltimos, pastdagi tugma orqali admin qiling, shunda barcha funksiyalar to'liq ishlaydi."
                ),
                reply_markup=kb,
                parse_mode='Markdown'
            )
        except Exception:
            pass


# ---------------------- DM: Broadcast ----------------------
async def track_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Har qanday PRIVATE chatdagi xabarni ko'rsak, u foydalanuvchini DBga upsert qilamiz."""
    try:
        await dm_upsert_user(update.effective_user)
    except Exception as e:
        log.warning(f"track_private upsert xatolik: {e}")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(OWNER & DM) Matnni barcha DM obunachilarga yuborish."""
    if update.effective_chat.type != "private":
        return await update.effective_message.reply_text("⛔ Эта команда только DM (приватный чат)е работает.")
    if not is_owner(update):
        return await update.effective_message.reply_text("⛔ Эта команда разрешена только владельцу бота.")
    text = " ".join(context.args).strip()
    if not text and update.effective_message.reply_to_message:
        text = update.effective_message.reply_to_message.text_html or update.effective_message.reply_to_message.caption_html
    if not text:
        return await update.effective_message.reply_text("Foydalanish: /broadcast Yangilanish matni")

    ids = await dm_all_ids()
    total = len(ids); ok = 0; fail = 0
    await update.effective_message.reply_text(f"📣 DM jo‘natish boshlandi. Jami foydalanuvchilar: {total}")
    for cid in list(ids):
        try:
            await context.bot.send_message(cid, text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            ok += 1
            await asyncio.sleep(0.05)
        except (Exception,) as e:
            # drop forbidden/bad users
            await dm_remove_user(cid)
            fail += 1
    await update.effective_message.reply_text(f"✅ Yuborildi: {ok} ta, ❌ xatolik: {fail} ta.")

async def broadcastpost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(OWNER & DM) Reply qilingan postni barcha DM obunachilarga yuborish."""
    if update.effective_chat.type != "private":
        return await update.effective_message.reply_text("⛔ Эта команда только DM (приватный чат)е работает.")
    if not is_owner(update):
        return await update.effective_message.reply_text("⛔ Эта команда разрешена только владельцу бота.")
    msg = update.effective_message.reply_to_message
    if not msg:
        return await update.effective_message.reply_text("Foydalanish: /broadcastpost — yubormoqchi bo‘lgan xabarga reply qiling.")

    ids = await dm_all_ids()
    total = len(ids); ok = 0; fail = 0
    await update.effective_message.reply_text(f"📣 DM post tarqatish boshlandi. Jami foydalanuvchilar: {total}")
    for cid in list(ids):
        try:
            await context.bot.copy_message(chat_id=cid, from_chat_id=msg.chat_id, message_id=msg.message_id)
            ok += 1
            await asyncio.sleep(0.05)
        except (Exception,) as e:
            await dm_remove_user(cid)
            fail += 1
    await update.effective_message.reply_text(f"✅ Yuborildi: {ok} ta, ❌ xatolik: {fail} ta.")

# ----------- Setup -----------
async def set_commands(app):
    await app.bot.set_my_commands(
        commands=[
            BotCommand("start", "О боте"),
            BotCommand("help", "Справка по командам"),
            BotCommand("id", "Показать ваш ID"),
            BotCommand("count", "Сколько людей вы добавили"),
            BotCommand("top", "ТОП 100 участников"),
            BotCommand("replycount", "(reply) сколько добавил пользователь"),
            BotCommand("forced", "Установить лимит обязательных приглашений (3–30)"),
            BotCommand("forcedoff", "Отключить обязательные приглашения"),
            BotCommand("cleangroup", "Обнулить все счётчики"),
            BotCommand("cleanuser", "(reply) обнулить счётчик пользователя"),
            BotCommand("permit", "(reply) выдать привилегию"),
            BotCommand("channel", "Настроить обязательный канал"),
            BotCommand("channeloff", "Отключить обязательный канал"),
            BotCommand("night", "Включить ночной режим"),
            BotCommand("nightoff", "Выключить ночной режим"),
],
        scope=BotCommandScopeAllPrivateChats()
    )

async def post_init(app):
    await init_db(app)
    # per-group tables (safety)
    try:
        await init_group_db()
    except Exception:
        pass
    await set_commands(app)


def main():
    start_web()
    app = ApplicationBuilder().token(TOKEN).build()
    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help))
    app.add_handler(CommandHandler("id", id_berish))
    app.add_handler(CommandHandler("tun", tun))
    app.add_handler(CommandHandler("night", tun))
    app.add_handler(CommandHandler("tunoff", tunoff))
    app.add_handler(CommandHandler("nightoff", tunoff))
    app.add_handler(CommandHandler("ruxsat", ruxsat))
    app.add_handler(CommandHandler("permit", ruxsat))
    app.add_handler(CommandHandler("kanal", kanal))
    app.add_handler(CommandHandler("channel", kanal))
    app.add_handler(CommandHandler("kanaloff", kanaloff))
    app.add_handler(CommandHandler("channeloff", kanaloff))
    app.add_handler(CommandHandler("majbur", majbur))
    app.add_handler(CommandHandler("forced", majbur))
    app.add_handler(CommandHandler("majburoff", majburoff))
    app.add_handler(CommandHandler("forcedoff", majburoff))
    app.add_handler(CommandHandler("top", top_cmd))
    app.add_handler(CommandHandler("cleangroup", cleangroup))
    app.add_handler(CommandHandler("count", count_cmd))
    app.add_handler(CommandHandler("replycount", replycount))
    app.add_handler(CommandHandler("cleanuser", cleanuser))

    # DM broadcast (owner only)
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("broadcastpost", broadcastpost))

    # Callbacks
    app.add_handler(CallbackQueryHandler(on_set_limit, pattern=r"^set_limit:"))
    app.add_handler(CallbackQueryHandler(kanal_callback, pattern=r"^kanal_azo(?::\d+)?$"))
    app.add_handler(CallbackQueryHandler(on_check_added, pattern=r"^check_added(?::\d+)?$"))
    app.add_handler(CallbackQueryHandler(on_grant_priv, pattern=r"^grant:"))
    app.add_handler(CallbackQueryHandler(lambda u,c: u.callback_query.answer(""), pattern=r"^noop$"))

     # Events & Filters
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_new_members))
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, on_left_member))
    media_filters = (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL | filters.ANIMATION | filters.VOICE | filters.VIDEO_NOTE | filters.GAME)
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE, track_private), group=-3)
    app.add_handler(MessageHandler(media_filters & (~filters.COMMAND), majbur_filter), group=-2)
    app.add_handler(MessageHandler(media_filters & (~filters.COMMAND), reklama_va_soz_filtri), group=-1)

   # Post-init hook
    app.post_init = post_init

    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
