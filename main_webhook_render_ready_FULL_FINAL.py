from telegram import Chat, Message, Update, BotCommand, BotCommandScopeAllPrivateChats, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ChatMemberHandler, ContextTypes, filters

import threading
import os
import re
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

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
    DB_POOL = await asyncpg.create_pool(dsn=db_url, min_size=1, max_size=5)
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
                                    "INSERT INTO dm_users (user_id) VALUES ($1) ON CONFLICT DO NOTHING;", cid_int
                                )
                    log.info(f"Migratsiya: JSON dan Postgresga {len(s)} ta ID import qilindi.")
    except Exception as e:
        log.warning(f"Migratsiya vaqtida xato: {e}")

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
    global TUN_REJIMI
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Только для администраторов.")
    TUN_REJIMI = True
    await update.effective_message.reply_text("🌙 Ночной режим включен. Сообщения пользователей будут удалены.")

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
        return await update.effective_message.reply_text("Пожалуйста, ОТВЕТЬте на сообщение пользователя.")
    uid = update.effective_message.reply_to_message.from_user.id
    RUXSAT_USER_IDS.add(uid)
    await update.effective_message.reply_text(f"✅ <code>{uid}</code> Пользователю разрешено.", parse_mode="HTML")

async def kanal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Только для администраторов.")
    global KANAL_USERNAME
    if context.args:
        KANAL_USERNAME = context.args[0]
        await update.effective_message.reply_text(f"📢 Обязательный канал: {KANAL_USERNAME}")
    else:
        await update.effective_message.reply_text("Образец: /Channel @username")

async def kanaloff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Только для администраторов.")
    global KANAL_USERNAME
    KANAL_USERNAME = None
    await update.effective_message.reply_text("🚫 Обязательное требование к каналу удалено.")

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
            if not (3 <= val <= 30):
                raise ValueError
            MAJBUR_LIMIT = val
            await update.effective_message.reply_text(
                f"✅ Обязательный лимит добавления лиц: <b>{MAJBUR_LIMIT}</b>",
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
    if not await is_admin(update):
        return await update.callback_query.answer("Только админы!", show_alert=True)
    q = update.callback_query
    await q.answer()
    data = q.data.split(":", 1)[1]
    global MAJBUR_LIMIT
    if data == "cancel":
        return await q.edit_message_text("❌ ОТМЕНЕНО.")
    try:
        val = int(data)
        if not (3 <= val <= 30):
            raise ValueError
        MAJBUR_LIMIT = val
        await q.edit_message_text(f"✅ Обязательный лимит: <b>{MAJBUR_LIMIT}</b>", parse_mode="HTML")
    except Exception:
        await q.edit_message_text("❌ Недопустимое значение.")

async def majburoff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Только для администраторов.")
    global MAJBUR_LIMIT
    MAJBUR_LIMIT = 0
    await update.effective_message.reply_text("🚫 Обязательное добавление лица было отключено..")

async def top_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Только для администраторов.")
    if not FOYDALANUVCHI_HISOBI:
        return await update.effective_message.reply_text("Пока никто никого не добавил.")
    items = sorted(FOYDALANUVCHI_HISOBI.items(), key=lambda x: x[1], reverse=True)[:100]
    lines = ["🏆 <b>ТОП 100 участников по добавлениям</b> (TOP 100):"]
    for i, (uid, cnt) in enumerate(items, start=1):
        lines.append(f"{i}. <code>{uid}</code> — {cnt} ta")
    await update.effective_message.reply_text("\n".join(lines), parse_mode="HTML")

async def cleangroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Только для администраторов.")
    FOYDALANUVCHI_HISOBI.clear()
    RUXSAT_USER_IDS.clear()
    await update.effective_message.reply_text("🗑 Счётчики и привилегии обнулены.")

async def count_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    cnt = FOYDALANUVCHI_HISOBI.get(uid, 0)
    if MAJBUR_LIMIT > 0:
        qoldi = max(MAJBUR_LIMIT - cnt, 0)
        await update.effective_message.reply_text(f"📊 Вы {cnt} шт добавили людей. Осталось: {осталось} шт.")
    else:
        await update.effective_message.reply_text(f"📊 Вы {cnt} шт добавили людей. (Принудительное добавление не активно)")

async def replycount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Только для админов.")
    msg = update.effective_message
    if not msg.reply_to_message:
        return await msg.reply_text("Пожалуйста, ОТВЕТЬте на сообщение, чей аккаунт вы хотите увидеть.")
    uid = msg.reply_to_message.from_user.id
    cnt = FOYDALANUVCHI_HISOBI.get(uid, 0)
    await msg.reply_text(f"👤 <code>{uid}</code> {cnt} шт добавил людей.", parse_mode="HTML")

async def cleanuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.effective_message.reply_text("⛔ Только для админов.")
    msg = update.effective_message
    if not msg.reply_to_message:
        return await msg.reply_text("Пожалуйста, ОТВЕТЬте на сообщение нужного вам пользователя 0.")
    uid = msg.reply_to_message.from_user.id
    FOYDALANUVCHI_HISOBI[uid] = 0
    RUXSAT_USER_IDS.discard(uid)
    await msg.reply_text(f"🗑 <code>{uid}</code> Счет пользователя сброшена до 0 (привилегия удалена).", parse_mode="HTML")

async def kanal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    if not KANAL_USERNAME:
        return await q.edit_message_text("⚠️ Канал не настроен.")
    try:
        member = await context.bot.get_chat_member(KANAL_USERNAME, user_id)
        if member.status in ("member", "administrator", "creator"):
            # ⬇️ To'liq ruxsat beramiz (guruh sozlamalari darajasida)
            try:
                await context.bot.restrict_chat_member(
                    chat_id=q.message.chat.id,
                    user_id=user_id,
                    permissions=FULL_PERMS,
                )
            except Exception:
                pass
            await q.edit_message_text("✅ Ваше членство подтверждено. Теперь вы можете публиковать сообщения в группе.")
        else:
            await q.edit_message_text("❌ Вы еще не являетесь участником канала.")
    except Exception:
        await q.edit_message_text("⚠️ Ошибка проверки. Неверное имя пользователя канала или бот не является участником канала.")

async def on_check_added(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id

    # faqat ogohlantirish olgan egasi bosa oladi
    data = q.data
    if ":" in data:
        try:
            owner_id = int(data.split(":", 1)[1])
        except ValueError:
            owner_id = None
        if owner_id and owner_id != uid:
            return await q.answer("Эта кнопка не для вас!", show_alert=True)

    cnt = FOYDALANUVCHI_HISOBI.get(uid, 0)

    # Talab bajarilgan holat: to'liq ruxsat
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
        return await q.edit_message_text("✅ Запрос выполнен! Теперь вы можете писать в группе.")

    # Yetarli emas holat: MODAL oynacha
    qoldi = max(MAJBUR_LIMIT - cnt, 0)
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
        target_id = int(q.data.split(":", 1)[1])
    except Exception:
        return await q.edit_message_text("❌ Неверная информация.")
    RUXSAT_USER_IDS.add(target_id)
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
    # Tun rejimi
    if TUN_REJIMI:
        try:
            await msg.delete()
        except:
            pass
        return
    # Kanal a'zoligi
    if not await kanal_tekshir(msg.from_user.id, context.bot):
        try:
            await msg.delete()
        except:
            pass
        kb = [
            [InlineKeyboardButton("✅ Я подписался", callback_data="kanal_azo")],
            [InlineKeyboardButton("➕ Добавить в группу", url=admin_add_link(context.bot.username))]
        ]
        await context.bot.send_message(
    chat_id=msg.chat_id,
    text=f"⚠️ {msg.from_user.mention_html()}, вы не подписаны на канал {KANAL_USERNAME}!",
    reply_markup=InlineKeyboardMarkup(kb),
    parse_mode="HTML"
)
        return

    text = msg.text or msg.caption or ""
    entities = msg.entities or msg.caption_entities or []

    # Inline bot orqali kelgan xabar — ko'pincha game reklama
    if getattr(msg, "via_bot", None):
        try:
            await msg.delete()
        except:
            pass
        await context.bot.send_message(
    chat_id=msg.chat_id,
    text=f"⚠️ {msg.from_user.mention_html()}, Скрытые ссылки запрещены!",
    reply_markup=add_to_group_kb(context.bot.username),
    parse_mode="HTML"
)
        return

    # Tugmalarda game/web-app/URL bo'lsa — blok
    if has_suspicious_buttons(msg):
        try:
            await msg.delete()
        except:
            pass
        await context.bot.send_message(
            chat_id=msg.chat_id,
            text="⚠️ GAME/veb-app реклама кнопок запрещена!",
            reply_markup=add_to_group_kb(context.bot.username)
        )
        return

    # Matndan o‘yin reklamasini aniqlash
    low = text.lower()
    if any(k in low for k in SUSPECT_KEYWORDS):
        try:
            await msg.delete()
        except:
            pass
        await context.bot.send_message(
            chat_id=msg.chat_id,
            text="⚠️ Реклама игр запрещена!",
            reply_markup=add_to_group_kb(context.bot.username)
        )
        return

    # Botlardan kelgan reklama/havola/game
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
    text=f"⚠️ {msg.from_user.mention_html()}, reklama/ssilka yuborish taqiqlangan!",
    reply_markup=add_to_group_kb(context.bot.username),
    parse_mode="HTML"
)
            return

    # Yashirin yoki aniq ssilkalar
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
    text=f"⚠️ {msg.from_user.mention_html()}, Скрытые ссылки запрещены!",
    reply_markup=add_to_group_kb(context.bot.username),
    parse_mode="HTML"
)
                return

    if any(x in low for x in ("t.me","telegram.me","@","www.","https://youtu.be","http://","https://")):
        try:
            await msg.delete()
        except:
            pass
        await context.bot.send_message(
    chat_id=msg.chat_id,
    text=f"⚠️ {msg.from_user.mention_html()}, Реклама/ссылки запрещены!",
    reply_markup=add_to_group_kb(context.bot.username),
    parse_mode="HTML"
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
    text=f"⚠️ {msg.from_user.mention_html()}, Нецензурная слово запрещена!",
    reply_markup=add_to_group_kb(context.bot.username),
    parse_mode="HTML"
)
        return

# Yangi a'zolarni qo'shganlarni hisoblash hamda kirdi/chiqdi xabarlarni o'chirish
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

# Majburiy qo'shish filtri — yetmaganlarda 5 daqiqaga blok ham qo'yiladi
async def majbur_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if MAJBUR_LIMIT <= 0:
        return
    msg = update.effective_message
    # 🔒 Linked kanalning avtomatik forward postlari — teginmaymiz
    try:
        if await is_linked_channel_autoforward(msg, context.bot):
            return
    except Exception:
        pass
    if not msg or not msg.from_user:
        return
    if await is_privileged_message(msg, context.bot):
        return

    uid = msg.from_user.id

    # Agar foydalanuvchi hanuz blokda bo'lsa — xabarini o'chirib, hech narsa yubormaymiz
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

    # Xabarni o'chiramiz
    try:
        await msg.delete()
    except:
        return

    # 1 daqiqaga blok
    until = datetime.now(timezone.utc) + timedelta(minutes=1)
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
    until_str = until.strftime('%H:%M')
    kb = [
        [InlineKeyboardButton("✅ Я добавил людей", callback_data=f"check_added:{uid}")],
        [InlineKeyboardButton("🎟 Выдать привилегию", callback_data=f"grant:{uid}")],
        [InlineKeyboardButton("➕ Добавить в группу", url=admin_add_link(context.bot.username))],
        [InlineKeyboardButton("⏳ заблокирован на минуту 1", callback_data="noop")]
    ]
    await context.bot.send_message(
        chat_id=msg.chat_id,
        text=f"⚠️ Для публикации в группе нужно добавить {MAJBUR_LIMIT} человека! Осталось: {qoldi}.",
        reply_markup=InlineKeyboardMarkup(kb)
    )
# -------------- Bot my_status (admin emas) ogohlantirish --------------
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
    app.add_handler(CallbackQueryHandler(kanal_callback, pattern=r"^kanal_azo$"))
    app.add_handler(CallbackQueryHandler(on_check_added, pattern=r"^check_added(?::\d+)?$"))
    app.add_handler(CallbackQueryHandler(on_grant_priv, pattern=r"^grant:"))
    app.add_handler(CallbackQueryHandler(lambda u,c: u.callback_query.answer(""), pattern=r"^noop$"))

     # Events & Filters
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_new_members))
    media_filters = (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL | filters.ANIMATION | filters.VOICE | filters.VIDEO_NOTE | filters.GAME)
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE, track_private), group=-3)
    app.add_handler(MessageHandler(media_filters & (~filters.COMMAND), majbur_filter), group=-2)
    app.add_handler(MessageHandler(media_filters & (~filters.COMMAND), reklama_va_soz_filtri), group=-1)

   # Post-init hook
    app.post_init = post_init

    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
