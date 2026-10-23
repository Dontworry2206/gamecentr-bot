"""Поиск игр в PS Store (регион ru-ua) и выбор издания для расчёта цены.

Страницы магазина рендерятся на сервере и содержат JSON-состояние (Apollo cache)
в тегах <script type="application/json">. Из него достаём продукты: название,
цену (обычную и со скидкой), классификацию и обложку.
"""

import difflib
import json
import re
from dataclasses import dataclass
from urllib.parse import quote

import aiohttp

REGION = "ru-ua"
BASE_URL = f"https://store.playstation.com/{REGION}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/129.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-UA,ru;q=0.9,uk;q=0.8,en;q=0.7",
}

# Что считаем «игрой», а не дополнением/валютой/темой
GAME_CLASSES = {"FULL_GAME", "PREMIUM_EDITION", "GAME_BUNDLE", "BUNDLE"}

# Порядок предпочтения обложек
IMAGE_ROLES = ["MASTER", "GAMEHUB_COVER_ART", "EDITION_KEY_ART", "PORTRAIT_BANNER", "FOUR_BY_THREE_BANNER"]

SCRIPT_RE = re.compile(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', re.S)


@dataclass
class Product:
    id: str
    name: str
    base_uah: float | None
    final_uah: float | None
    discount_text: str | None
    image: str | None
    classification: str | None

    @property
    def on_sale(self) -> bool:
        return (
            self.base_uah is not None
            and self.final_uah is not None
            and self.final_uah < self.base_uah
        )

    @property
    def url(self) -> str:
        return f"{BASE_URL}/product/{self.id}"


def parse_price(text) -> float | None:
    """'UAH 1 299', '1 299,00 грн', 'UAH1,299.00' -> 1299.0. 'Бесплатно' -> 0."""
    if text is None:
        return None
    s = str(text)
    if not re.search(r"\d", s):
        return 0.0 if re.search(r"бесплат|безкошт|free", s, re.I) else None
    s = re.sub(r"[^\d.,]", "", s)
    # Десятичная часть — последний разделитель, за которым ровно 2 цифры
    m = re.match(r"^(.*?)[.,](\d{2})$", s)
    if m:
        whole, frac = m.group(1), m.group(2)
    else:
        whole, frac = s, "0"
    whole = re.sub(r"[.,]", "", whole)
    if not whole:
        return None
    return float(f"{whole}.{frac}")


def _json_blobs(html: str):
    for raw in SCRIPT_RE.findall(html):
        try:
            yield json.loads(raw)
        except ValueError:
            continue


def _walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def _collect_refs(blobs) -> dict:
    """Все записи Apollo-кэша вида {'Product:XXX': {...}} для разрешения __ref."""
    refs = {}
    for blob in blobs:
        for d in _walk(blob):
            for k, v in d.items():
                if isinstance(v, dict) and ":" in k and "__typename" in v:
                    refs[k] = v
    return refs


def _deref(value, refs):
    if isinstance(value, dict) and "__ref" in value:
        return refs.get(value["__ref"], {})
    return value


def _pick_image(media, refs) -> str | None:
    media = [_deref(m, refs) for m in (_deref(media, refs) or [])]
    images = [m for m in media if isinstance(m, dict) and m.get("url") and m.get("type", "IMAGE") == "IMAGE"]
    for role in IMAGE_ROLES:
        for m in images:
            if m.get("role") == role:
                return m["url"]
    return images[0]["url"] if images else None


def extract_products(html: str) -> list[Product]:
    blobs = list(_json_blobs(html))
    refs = _collect_refs(blobs)
    found: dict[str, Product] = {}
    for blob in blobs:
        for d in _walk(blob):
            if d.get("__typename") not in (None, "Product") or not d.get("name"):
                continue
            price = _deref(d.get("price"), refs)
            if not isinstance(price, dict) or "basePrice" not in price:
                continue
            pid = d.get("id")
            if not pid:
                continue
            base = parse_price(price.get("basePrice"))
            final = parse_price(price.get("discountedPrice")) if price.get("discountedPrice") else base
            if price.get("isFree"):
                base = final = 0.0
            # Скидка только для подписчиков PS Plus — нам не подходит
            if "PS_PLUS" in (price.get("serviceBranding") or []) and final != base:
                final = base
            prod = Product(
                id=pid,
                name=d["name"].strip(),
                base_uah=base,
                final_uah=final,
                discount_text=price.get("discountText") if final != base else None,
                image=_pick_image(d.get("media"), refs),
                classification=d.get("storeDisplayClassification"),
            )
            old = found.get(pid)
            if old is None or (old.image is None and prod.image):
                found[pid] = prod
    return list(found.values())


def _norm(s: str) -> str:
    s = s.lower().replace("ё", "е")
    s = re.sub(r"[™®©:'’\-–—.,!?]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


EDITION_WORDS = re.compile(
    r"\b(standard|deluxe|ultimate|gold|premium|complete|digital|edition|bundle|"
    r"издание|делюкс|стандартное|полное|расширенное|золотое|комплект)\b.*$"
)


def _games(products: list[Product]) -> list[Product]:
    return [p for p in products if p.classification in GAME_CLASSES or p.classification is None]


ROMAN = {"1": "i", "2": "ii", "3": "iii", "4": "iv", "5": "v", "6": "vi", "7": "vii", "8": "viii", "9": "ix", "10": "x"}


def _token_matches(token: str, name: str, words: list[str]) -> bool:
    if token in name or ROMAN.get(token) in words:
        return True
    # Опечатки: «eldn» ~ «elden», «spiderman» ~ «spider»
    if len(token) >= 3 and not token.isdigit():
        return any(difflib.SequenceMatcher(None, token, w).ratio() >= 0.75 for w in words)
    return False


def _relevant(products: list[Product], query: str) -> list[Product]:
    tokens = _norm(query).split()
    out = []
    for p in _games(products):
        name = _norm(p.name)
        words = name.split()
        if all(_token_matches(t, name, words) for t in tokens):
            out.append(p)
    return out


def _base_title(name: str) -> str:
    """'ELDEN RING Deluxe Edition' -> 'elden ring'."""
    return EDITION_WORDS.sub("", _norm(name)).strip() or _norm(name)


async def _get(session: aiohttp.ClientSession, url: str) -> str:
    async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=25)) as r:
        r.raise_for_status()
        return await r.text()


async def find_cheapest(query: str) -> Product | None:
    """Самая дешёвая платная игра среди результатов поиска (например, «LEGO»)."""
    async with aiohttp.ClientSession() as session:
        html = await _get(session, f"{BASE_URL}/search/{quote(query)}")
    games = _relevant(extract_products(html), query)
    paid = [p for p in games if p.final_uah]
    return min(paid, key=lambda p: p.final_uah) if paid else None


async def find_game(query: str) -> tuple[Product | None, list[Product]]:
    """Возвращает (выбранное издание, все найденные издания этой игры)."""
    async with aiohttp.ClientSession() as session:
        html = await _get(session, f"{BASE_URL}/search/{quote(query)}")
        search_results = extract_products(html)
        candidates = _relevant(search_results, query)
        if not candidates:
            # Запрос написан иначе, чем в магазине (например «гта 5») —
            # доверяем первому игровому результату поиска
            games = _games(search_results)
            if not games:
                return None, []
            query = _base_title(games[0].name)
            candidates = _relevant(search_results, query) or games[:1]

        # В поиске обычно одно издание на игру — со страницы продукта
        # подтягиваем остальные (Deluxe, Ultimate и т.д.)
        top = candidates[0]
        try:
            page = await _get(session, top.url)
            merged = {p.id: p for p in candidates}
            for p in _relevant(extract_products(page), query):
                merged.setdefault(p.id, p)
            candidates = list(merged.values())
        except aiohttp.ClientError:
            pass

    priced = [p for p in candidates if p.final_uah is not None]
    if not priced:
        return None, candidates
    chosen = choose_edition(priced)
    if not chosen.image:
        chosen.image = next((p.image for p in candidates if p.image), None)
    return chosen, priced


def choose_edition(products: list[Product]) -> Product:
    """Есть скидки — самое дешёвое издание по акции. Нет — самое полное (дорогое) издание."""
    sale = [p for p in products if p.on_sale]
    if sale:
        return min(sale, key=lambda p: p.final_uah)
    return max(products, key=lambda p: p.base_uah or 0)
