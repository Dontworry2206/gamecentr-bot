"""Telegram-бот GameCentr: присылаете название игры (или список, или фото) — получаете цену в UZS и обложку."""

import asyncio
import html
import io
import logging
import os

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from nlp import CHEAPEST, Request, ai_enabled, parse_message, parse_photo, search_variants
from pricing import PS_PLUS_TEXT, fmt_uzs, uah_to_uzs
from store import Product, edition_matches, find_cheapest, find_game

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("gamecentr")

dp = Dispatcher()


def load_env():
    if not os.path.exists(".env"):
        return
    with open(".env", encoding="utf-8") as f:
        for line in f:
            key, _, value = line.strip().partition("=")
            if key and value and not key.startswith("#"):
                os.environ.setdefault(key.strip(), value.strip().strip('"'))


@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "👋 Отправьте название игры — я найду её в PS Store (Украина) и посчитаю цену в UZS.\n\n"
        "Можно:\n"
        "• по-русски и с опечатками: <i>ведьмак</i>, <i>гта 5</i>, <i>элден ринг</i>\n"
        "• списком — каждая игра с новой строки\n"
        "• <i>найди самую дешёвую игру lego</i>\n"
        "• фото обложки или скриншот игры\n\n"
        "/psplus — цены на подписки PS Plus и EA Play"
    )


@dp.message(Command("psplus"))
async def psplus(message: Message):
    await message.answer(PS_PLUS_TEXT)


async def lookup(req: Request) -> list[Product]:
    """Пробуем варианты запроса: исходный, русский алиас, транслит."""
    for query in search_variants(req.query):
        if req.mode == CHEAPEST:
            products = await find_cheapest(query, req.count, req.exclude_plus)
        else:
            product, _ = await find_game(query, req.edition or None)
            products = [product] if product else []
        if products:
            for p in products:
                log.info("%r [%s %s] -> %r: %s, %s грн (база %s)", req.original or req.query, req.mode,
                         req.edition, query, p.name, p.final_uah, p.base_uah)
            return products
    log.info("%r [%s] -> не найдено", req.original or req.query, req.mode)
    return []


def price_line(product: Product) -> str:
    if product.final_uah == 0:
        return "Бесплатно"
    return fmt_uzs(uah_to_uzs(product.final_uah))


def caption_for(product: Product, req: Request) -> str:
    lines = []
    if req.mode == CHEAPEST:
        lines.append(f"🏷 Самая дешёвая по запросу «{html.escape(req.query)}»:")
    lines.append(f"🎮 <b>{html.escape(product.name)}</b>")
    lines.append("")
    lines.append(f"💰 Цена: <b>{price_line(product)}</b>")
    if product.final_uah and product.on_sale:
        sale = f"🔥 Скидка {product.discount_text}" if product.discount_text else "🔥 Скидка"
        lines.append(f"{sale} (без скидки {fmt_uzs(uah_to_uzs(product.base_uah))})")
    if req.edition and not edition_matches(product.name, req.edition):
        lines.append(f"\n⚠️ Издания {req.edition.title()} в магазине нет — показал доступное.")
    return "\n".join(lines)


def collection_caption(products: list[Product], req: Request) -> str:
    title = f"🏷 Самые дешёвые по запросу «{html.escape(req.query)}»"
    if req.exclude_plus:
        title += " (без игр из PS Plus)"
    lines = [title + ":", ""]
    for i, p in enumerate(products, 1):
        sale = f" 🔥 {html.escape(p.discount_text)}" if p.on_sale and p.discount_text else ""
        lines.append(f"{i}. <b>{html.escape(p.name)}</b> — {price_line(p)}{sale}")
    return "\n".join(lines)


async def send_product(message: Message, product: Product, req: Request, caption: str | None = None):
    caption = caption or caption_for(product, req)
    if product.image:
        try:
            await message.answer_photo(product.image, caption=caption)
            return
        except Exception as e:  # Telegram не смог скачать картинку — отправим текстом
            log.warning("Не удалось отправить фото %s: %r", product.image, e)
    await message.answer(caption)


async def answer_requests(message: Message, requests: list[Request], wait: Message):
    if not requests:
        await wait.edit_text("🤔 Не нашёл в сообщении названия игры. Напишите, например: <i>God of War</i>")
        return

    found: list[tuple[Request, Product]] = []
    missing: list[Request] = []
    collections: list[Request] = []
    for i, req in enumerate(requests, 1):
        if len(requests) > 1:
            await wait.edit_text(f"🔎 Ищу {i} из {len(requests)}: «{html.escape(req.query)}»...")
        try:
            products = await lookup(req)
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            log.warning("Ошибка запроса к PS Store: %r", e)
            products = []
        if not products:
            missing.append(req)
        elif req.count > 1:
            # Подборка — одно сообщение с обложкой самой дешёвой игры; в итог не входит
            await send_product(message, products[0], req, collection_caption(products, req))
            collections.append(req)
        else:
            found.append((req, products[0]))
            await send_product(message, products[0], req)

    await wait.delete()
    if len(requests) > 1 and found:
        total = sum(uah_to_uzs(p.final_uah) for _, p in found if p.final_uah)
        lines = [f"🧾 <b>Итого по {len(found)} играм: {fmt_uzs(total)}</b>"]
        for _, p in found:
            price = "бесплатно" if p.final_uah == 0 else fmt_uzs(uah_to_uzs(p.final_uah))
            lines.append(f"• {html.escape(p.name)} — {price}")
        if collections:
            lines.append("")
            lines.append("📋 Подборки (в итог не входят): " + ", ".join(f"«{html.escape(r.query)}»" for r in collections))
        if missing:
            lines.append("")
            lines.append("😔 Не нашёл: " + ", ".join(f"«{html.escape(r.original or r.query)}»" for r in missing))
        await message.answer("\n".join(lines))
    elif missing and len(requests) > 1:
        await message.answer("😔 Не нашёл: " + ", ".join(f"«{html.escape(r.original or r.query)}»" for r in missing))
    elif missing:
        await message.answer(
            f"😔 Игра «{html.escape(missing[0].original or missing[0].query)}» не найдена. "
            "Попробуйте написать название как в PS Store."
        )


@dp.message(F.text & ~F.text.startswith("/"))
async def on_text(message: Message):
    wait = await message.answer("🔎 Ищу...")
    requests = await parse_message(message.text)
    await answer_requests(message, requests, wait)


@dp.message(F.photo)
async def on_photo(message: Message, bot: Bot):
    if not ai_enabled():
        await message.answer(
            "📷 Распознавание фото включается ключом Claude API (ANTHROPIC_API_KEY в .env). "
            "Пока напишите название игры текстом."
        )
        return
    wait = await message.answer("📷 Смотрю фото...")
    buf = io.BytesIO()
    await bot.download(message.photo[-1], destination=buf)
    requests = await parse_photo(buf.getvalue(), message.caption)
    if requests is None:
        await wait.edit_text("⚠️ Не получилось распознать фото, напишите название игры текстом.")
        return
    await answer_requests(message, requests, wait)


async def main():
    load_env()
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit("Укажите BOT_TOKEN в файле .env или в переменной окружения")
    log.info("Claude API: %s", "включён" if ai_enabled() else "выключен (разбор по правилам)")
    bot = Bot(token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
