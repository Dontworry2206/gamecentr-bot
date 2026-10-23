"""Разбор сообщений: список игр столбиком, русские названия, опечатки, «самая дешёвая игра LEGO».

Без ключа Claude API работает по правилам (словарь русских названий, транслит,
распознавание «дешёвая»). С ANTHROPIC_API_KEY запрос сначала разбирает Claude:
он понимает любые формулировки и исправляет опечатки.
"""

from __future__ import annotations

import difflib
import json
import logging
import os
import re
from dataclasses import dataclass

log = logging.getLogger("gamecentr.nlp")

MAX_ITEMS = 30

# Режимы: best — скидка, иначе самое полное издание; cheapest — самая дешёвая игра из найденных
BEST, CHEAPEST = "best", "cheapest"


@dataclass
class Request:
    query: str
    mode: str = BEST
    original: str = ""
    edition: str = ""  # издание, которое просили явно: ultimate, deluxe, gold...
    count: int = 1  # сколько игр вернуть в режиме cheapest («подборка» — несколько)
    exclude_plus: bool = False  # не предлагать игры из каталога PS Plus


# Народные и русские названия -> название в PS Store
ALIASES = {
    "гта": "Grand Theft Auto V",
    "гта 5": "Grand Theft Auto V",
    "гта 6": "Grand Theft Auto VI",
    "gta": "Grand Theft Auto V",
    "gta 5": "Grand Theft Auto V",
    "gta v": "Grand Theft Auto V",
    "gta 6": "Grand Theft Auto VI",
    "rdr 2": "Red Dead Redemption 2",
    "gow": "God of War",
    "tlou": "The Last of Us",
    "mk 1": "Mortal Kombat 1",
    "mk 11": "Mortal Kombat 11",
    "fc 25": "EA SPORTS FC 25",
    "fc 26": "EA SPORTS FC 26",
    "fifa 25": "EA SPORTS FC 25",
    "fifa 26": "EA SPORTS FC 26",
    "ufc 5": "EA SPORTS UFC 5",
    "rdr": "Red Dead Redemption 2",
    "cod": "Call of Duty",
    "рдр": "Red Dead Redemption 2",
    "рдр 2": "Red Dead Redemption 2",
    "ред дед": "Red Dead Redemption 2",
    "ред дед редемпшн 2": "Red Dead Redemption 2",
    "фифа": "EA SPORTS FC",
    "фк": "EA SPORTS FC",
    "фк 25": "EA SPORTS FC 25",
    "фк 26": "EA SPORTS FC 26",
    "фифа 25": "EA SPORTS FC 25",
    "фифа 26": "EA SPORTS FC 26",
    "пес": "eFootball",
    "кал оф дьюти": "Call of Duty",
    "колда": "Call of Duty",
    "калда": "Call of Duty",
    "человек паук": "Marvel's Spider-Man",
    "спайдер мен": "Marvel's Spider-Man",
    "человек паук 2": "Marvel's Spider-Man 2",
    "майлз моралес": "Marvel's Spider-Man: Miles Morales",
    "ведьмак": "The Witcher 3: Wild Hunt",
    "ведьмак 3": "The Witcher 3: Wild Hunt",
    "одни из нас": "The Last of Us",
    "ласт оф ас": "The Last of Us",
    "одни из нас 2": "The Last of Us Part II",
    "бог войны": "God of War",
    "год оф вар": "God of War",
    "гов": "God of War",
    "рагнарек": "God of War Ragnarök",
    "элден ринг": "ELDEN RING",
    "элден": "ELDEN RING",
    "мортал комбат": "Mortal Kombat 1",
    "мк": "Mortal Kombat 1",
    "мк 1": "Mortal Kombat 1",
    "мортал комбат 11": "Mortal Kombat 11",
    "теккен": "TEKKEN 8",
    "теккен 8": "TEKKEN 8",
    "киберпанк": "Cyberpunk 2077",
    "ассасин": "Assassin's Creed",
    "ассасин крид": "Assassin's Creed",
    "ассасины": "Assassin's Creed",
    "фар край": "Far Cry",
    "форза": "Forza Horizon 5",
    "форза хорайзон": "Forza Horizon 5",
    "гран туризмо": "Gran Turismo 7",
    "гт 7": "Gran Turismo 7",
    "нфс": "Need for Speed",
    "need for speed": "Need for Speed",
    "нид фор спид": "Need for Speed",
    "резидент ивел": "Resident Evil",
    "резидент": "Resident Evil",
    "обитель зла": "Resident Evil",
    "майнкрафт": "Minecraft",
    "фортнайт": "Fortnite",
    "хогвартс": "Hogwarts Legacy",
    "хогвартс легаси": "Hogwarts Legacy",
    "гарри поттер": "Hogwarts Legacy",
    "призрак цусимы": "Ghost of Tsushima",
    "цусима": "Ghost of Tsushima",
    "гост оф цусима": "Ghost of Tsushima",
    "призрак йотея": "Ghost of Yōtei",
    "детройт": "Detroit: Become Human",
    "хорайзон": "Horizon Forbidden West",
    "хорайзон форбидден вест": "Horizon Forbidden West",
    "дэс стрендинг": "DEATH STRANDING",
    "даинг лайт": "Dying Light",
    "дайнг лайт": "Dying Light",
    "сайлент хилл": "SILENT HILL",
    "батлфилд": "Battlefield",
    "бф": "Battlefield",
    "уфс": "EA SPORTS UFC 5",
    "юфс": "EA SPORTS UFC 5",
    "нба": "NBA 2K",
    "нхл": "NHL",
    "f1": "F1",
    "ф1": "F1",
    "крэш": "Crash Bandicoot",
    "спайро": "Spyro",
    "астро бот": "ASTRO BOT",
    "астробот": "ASTRO BOT",
    "стеллар блейд": "Stellar Blade",
    "блек миф": "Black Myth: Wukong",
    "вуконг": "Black Myth: Wukong",
    "сифу": "Sifu",
    "ит тейкс ту": "It Takes Two",
    "сплит фикшн": "Split Fiction",
    "скайрим": "The Elder Scrolls V: Skyrim",
    "фоллаут": "Fallout",
    "дум": "DOOM",
    "мафия": "Mafia",
    "вотч догс": "Watch Dogs",
    "дьябло": "Diablo IV",
    "диабло": "Diablo IV",
    "лего": "LEGO",
    "бэтмен": "Batman",
    "бетмен": "Batman",
    "сонник": "Sonic",
    "соник": "Sonic",
    "пэкмен": "PAC-MAN",
    "пакман": "PAC-MAN",
    "овервотч": "Overwatch 2",
    "апекс": "Apex Legends",
    "роблокс": "Roblox",
    "тлоу": "The Last of Us",
    "уно": "UNO",
    "монополия": "MONOPOLY",
    "ну и погодка": "Overcooked",
    "оверкукед": "Overcooked",
}

_TRANSLIT = dict(zip(
    "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
    ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p",
     "r", "s", "t", "u", "f", "h", "ts", "ch", "sh", "sch", "", "y", "", "e", "yu", "ya"],
))

CHEAP_RE = re.compile(r"\b(с[а-я]*\s+)?((деш|диш)[ёеоo]в\w*|подешевле|cheap\w*|минимальн\w*|недорог\w*)\b", re.I)

FILLER_RE = re.compile(
    r"\b(найди|найти|найдите|поищи|ищи|покажи|скинь|скажи|дай|подскажи|хочу|нужна|нужен|нужно|"
    r"сколько|стоит|стоят|цена|цену|цены|прайс|какая|какой|какие|мне|пожалуйста|плиз|pls|please|"
    r"игру|игра|игры|игре|игр|игрушку|из|серии|серия|про|на|в|по|ps5|ps4|пс5|пс4|ps|пс|"
    r"самую|самый|самое|самая|самые|price|find|game|games|the)\b",
    re.I,
)

LIST_MARK_RE = re.compile(r"^\s*(\d+[.)]|[-•*–—])\s*")

# Сокращения и русские названия изданий -> каноническое слово (см. store.EDITION_NAME_RE)
EDITIONS = {
    "ult": "ultimate", "ulti": "ultimate", "ultimate": "ultimate", "ультимейт": "ultimate",
    "ультимат": "ultimate", "ульта": "ultimate", "ульт": "ultimate",
    "deluxe": "deluxe", "dlx": "deluxe", "delux": "deluxe", "делюкс": "deluxe", "делакс": "deluxe",
    "gold": "gold", "голд": "gold", "золотое": "gold", "золотая": "gold",
    "premium": "premium", "премиум": "premium",
    "complete": "complete", "definitive": "complete", "полное": "complete", "комплит": "complete",
    "goty": "goty",
    "cross-gen": "cross-gen",
    "standard": "standard", "standart": "standard", "стандарт": "standard", "стандартное": "standard",
}
EDITION_FILLER = {"edition", "ed", "издание", "версия", "version", "издания"}

COLLECTION_RE = re.compile(r"подборк\w*|\bтоп\s*(\d+)?|\bсписок\b|несколько|(деш|диш)[ёеоo]в(ые|ых)\b", re.I)
COLLECTION_SIZE = 5

_PLUS_WORD = r"(подписк\w*|ps\s*plus|пс\s*плюс|плюс\w*|plus|extra|экстра)"
NO_PLUS_RE = re.compile(
    # «(каких нет в подписке)» целиком или «без ps plus», «не в подписке» в тексте
    r"\([^()]*\b(нет|не|без|кроме)\b[^()]*" + _PLUS_WORD + r"[^()]*\)"
    r"|\b(нет|не|без|кроме)\b(\s+[\w-]+){0,3}?\s+" + _PLUS_WORD,
    re.I,
)


def transliterate(text: str) -> str:
    return "".join(_TRANSLIT.get(ch, _TRANSLIT.get(ch.lower(), ch)) for ch in text)


def has_cyrillic(text: str) -> bool:
    return bool(re.search(r"[а-яё]", text, re.I))


def split_edition(query: str) -> tuple[str, str]:
    """'Tekken 8 ultimate' -> ('Tekken 8', 'ultimate'). 'Astro bot' -> ('Astro bot', '')."""
    words, edition = [], ""
    for w in query.split():
        key = w.lower().strip(".,")
        if key in EDITIONS and not edition:
            edition = EDITIONS[key]
        elif not (edition and key in EDITION_FILLER):
            words.append(w)
    if not words:  # запрос из одного слова-издания — не трогаем
        return query, ""
    return " ".join(words), edition


def _clean(text: str) -> Request:
    req = Request(query="", original=text)
    if NO_PLUS_RE.search(text):
        req.exclude_plus = True
        text = NO_PLUS_RE.sub(" ", text)
    collection = COLLECTION_RE.search(text)
    if collection:
        req.mode = CHEAPEST
        req.count = min(int(collection.group(1)), 10) if collection.group(1) else COLLECTION_SIZE
        text = COLLECTION_RE.sub(" ", text)
    if CHEAP_RE.search(text):
        req.mode = CHEAPEST
        text = CHEAP_RE.sub(" ", text)
    text = FILLER_RE.sub(" ", text)
    text = re.sub(r"\b(каких|которых|которые|что)\b", " ", text, flags=re.I)
    text = re.sub(r"[?!.,()]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    req.query, req.edition = split_edition(text)
    return req


def split_digits(text: str) -> str:
    """'гта5' -> 'гта 5', 'fc26' -> 'fc 26'."""
    return re.sub(r"(?<=[^\W\d_])(?=\d)|(?<=\d)(?=[^\W\d_])", " ", text)


def alias(query: str) -> str | None:
    key = re.sub(r"[-–—:]", " ", split_digits(query).lower().replace("ё", "е"))
    key = re.sub(r"\s+", " ", key).strip()
    if key in ALIASES:
        return ALIASES[key]
    # Опечатки в русском названии: «ведьмк», «киберпак»
    close = difflib.get_close_matches(key, ALIASES.keys(), n=1, cutoff=0.8)
    if close:
        return ALIASES[close[0]]
    # «гта 5 премиум» -> алиас первой части + остаток
    words = key.split()
    for n in range(len(words) - 1, 0, -1):
        head = " ".join(words[:n])
        if head in ALIASES:
            return f"{ALIASES[head]} {' '.join(words[n:])}"
    return None


def search_variants(query: str) -> list[str]:
    """Варианты поискового запроса в порядке приоритета."""
    variants = []
    a = alias(query)
    if a:
        variants.append(a)
    variants.append(query)
    if split_digits(query) != query:
        variants.append(split_digits(query))
    if has_cyrillic(query):
        variants.append(transliterate(query))
    seen, out = set(), []
    for v in variants:
        if v and v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    return out


def split_lines(text: str) -> list[str]:
    parts = re.split(r"[\n;]+", text)
    items = [LIST_MARK_RE.sub("", p).strip() for p in parts]
    return [i for i in items if i][:MAX_ITEMS]


def parse_rules(text: str) -> list[Request]:
    requests = []
    for line in split_lines(text):
        req = _clean(line)
        if req.query:
            requests.append(req)
    return requests


# ---------------------------------------------------------------- Claude ---

SYSTEM_PROMPT = """Ты помогаешь продавцу игр для PlayStation. Пользователь пишет в Telegram названия игр \
(по одной или списком столбиком), часто по-русски, сленгом, с опечатками, или просьбы вроде \
«найди самую дешёвую игру lego».

Для каждой игры из сообщения верни:
- query — точное официальное название игры так, как оно написано в PlayStation Store \
(обычно английское: «гта 5» → «Grand Theft Auto V», «ведьмак» → «The Witcher 3: Wild Hunt», \
«элден ринг» → «ELDEN RING»). Исправляй опечатки. Не добавляй издание (Deluxe и т.п.), \
если пользователь сам его не назвал. Для запросов про серию или бренд («игры lego», «колда») \
верни название серии: «LEGO», «Call of Duty».
- edition — издание, если пользователь его назвал, одним словом: ultimate («ult», «ульта»), deluxe, \
gold, premium, complete, goty, standard. Иначе пустая строка. В query издание не пиши.
- mode — "cheapest", если просят самую дешёвую игру/вариант (дешёвая, подешевле, минимальная цена); \
иначе "best".
- count — сколько игр вернуть: 1, а если просят подборку, список, топ или «самые дешёвые» во \
множественном числе — 5 (или названное число, максимум 10).
- exclude_plus — true, если просят игры, которых нет в подписке PS Plus («каких нет в подписке»).
- original — исходный фрагмент сообщения.

Пример: «Street fighter 6 ult» → query «Street Fighter 6», edition «ultimate». \
«Lego самые дешевые подборка(каких нет в подписке)» → query «LEGO», mode «cheapest», count 5, \
exclude_plus true.

Если в сообщении нет ни одной игры (приветствие, вопрос не про игры), верни пустой список."""

SCHEMA = {
    "type": "object",
    "properties": {
        "requests": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "mode": {"type": "string", "enum": [BEST, CHEAPEST]},
                    "original": {"type": "string"},
                    "edition": {"type": "string"},
                    "count": {"type": "integer"},
                    "exclude_plus": {"type": "boolean"},
                },
                "required": ["query", "mode", "original", "edition", "count", "exclude_plus"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["requests"],
    "additionalProperties": False,
}

_client = None


def _claude():
    global _client
    if _client is None and os.environ.get("ANTHROPIC_API_KEY"):
        import anthropic

        _client = anthropic.AsyncAnthropic()
    return _client


PHOTO_PROMPT = """На фото — игра (обложка, диск, скриншот из магазина или список игр). \
Определи, какие игры на нём, и верни их так же, как для текстового сообщения. \
Издание (Deluxe и т.п.) указывай, только если оно явно видно на фото."""


def ai_enabled() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


async def parse_claude(text: str, image: bytes | None = None, media_type: str = "image/jpeg") -> list[Request] | None:
    client = _claude()
    if client is None:
        return None
    import anthropic
    import base64

    content = [{"type": "text", "text": text}]
    if image is not None:
        content.insert(0, {
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": base64.standard_b64encode(image).decode()},
        })
    try:
        response = await client.beta.messages.create(
            model=os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5"),
            max_tokens=4000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )
    except anthropic.APIError as e:
        log.warning("Claude API недоступен, разбираю по правилам: %r", e)
        return None
    if response.stop_reason != "end_turn":
        log.warning("Claude не ответил (stop_reason=%s), разбираю по правилам", response.stop_reason)
        return None
    raw = next((b.text for b in response.content if b.type == "text"), "")
    try:
        items = json.loads(raw)["requests"]
    except (ValueError, KeyError):
        return None
    requests = []
    for i in items[:MAX_ITEMS]:
        if not i.get("query"):
            continue
        req = Request(**i)
        req.edition = EDITIONS.get(req.edition.lower().strip(), req.edition.lower().strip())
        req.count = max(1, min(req.count, 10))
        requests.append(req)
    return requests


async def parse_photo(image: bytes, caption: str | None) -> list[Request] | None:
    """None — распознать нечем (нет ключа или ошибка API)."""
    text = PHOTO_PROMPT + (f"\n\nПодпись к фото: {caption}" if caption else "")
    return await parse_claude(text, image=image)


async def parse_message(text: str) -> list[Request]:
    parsed = await parse_claude(text)
    if parsed is not None:
        return parsed
    return parse_rules(text)
