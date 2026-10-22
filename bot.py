"""Telegram-бот GameCentr: присылаете название игры — получаете цену в UZS и обложку."""

import asyncio
import html
import logging
import os

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from pricing import PS_PLUS_TEXT, fmt_uzs, uah_to_uzs
from store import find_game

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("gamecentr")

dp = Dispatcher()


def load_token() -> str:
    token = os.environ.get("BOT_TOKEN")
    if not token and os.path.exists(".env"):
        with open(".env", encoding="utf-8") as f:
            for line in f:
                key, _, value = line.strip().partition("=")
                if key == "BOT_TOKEN":
                    token = value.strip().strip('"')
    if not token:
        raise SystemExit("Укажите BOT_TOKEN в файле .env или в переменной окружения")
    return token


@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "👋 Отправьте название игры — я найду её в PS Store (Украина) и посчитаю цену в UZS.\n\n"
        "/psplus — цены на подписки PS Plus и EA Play"
    )


@dp.message(Command("psplus"))
async def psplus(message: Message):
    await message.answer(PS_PLUS_TEXT)


@dp.message(F.text & ~F.text.startswith("/"))
async def game_price(message: Message):
    query = message.text.strip()
    wait = await message.answer(f"🔎 Ищу «{html.escape(query)}»...")
    try:
        product, editions = await find_game(query)
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        log.warning("Ошибка запроса к PS Store: %r", e)
        await wait.edit_text("⚠️ PS Store сейчас не отвечает, попробуйте ещё раз через минуту.")
        return

    if product is None:
        await wait.edit_text("😔 Игра не найдена. Проверьте название (лучше писать как в PS Store, на английском).")
        return

    log.info(
        "%r -> %s | %s грн (база %s) | изданий: %d",
        query, product.name, product.final_uah, product.base_uah, len(editions),
    )

    lines = [f"🎮 <b>{html.escape(product.name)}</b>", ""]
    if product.final_uah == 0:
        lines.append("💰 Цена: <b>Бесплатно</b>")
    else:
        lines.append(f"💰 Цена: <b>{fmt_uzs(uah_to_uzs(product.final_uah))}</b>")
        if product.on_sale:
            sale = f"🔥 Скидка {product.discount_text}" if product.discount_text else "🔥 Скидка"
            lines.append(f"{sale} (без скидки {fmt_uzs(uah_to_uzs(product.base_uah))})")
    caption = "\n".join(lines)

    await wait.delete()
    if product.image:
        try:
            await message.answer_photo(product.image, caption=caption)
            return
        except Exception as e:  # Telegram не смог скачать картинку — отправим текстом
            log.warning("Не удалось отправить фото %s: %r", product.image, e)
    await message.answer(caption)


async def main():
    bot = Bot(load_token(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
