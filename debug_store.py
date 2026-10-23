"""Диагностика поиска в PS Store: python debug_store.py "Tekken 8"

Показывает, что вернул магазин, сколько игр удалось разобрать, и сохраняет
страницу в debug_search.html, чтобы её можно было посмотреть.
"""

import asyncio
import sys
from urllib.parse import quote

import aiohttp

from store import BASE_URL, HEADERS, SCRIPT_RE, extract_products


async def main(query: str):
    url = f"{BASE_URL}/search/{quote(query)}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=25)) as r:
            text = await r.text()
            print(f"Адрес:        {url}")
            print(f"Ответ:        HTTP {r.status}, итоговый адрес {r.url}")
            print(f"Размер:       {len(text)} символов")
    print(f"JSON-блоков:  {len(SCRIPT_RE.findall(text))}")
    print(f"__NEXT_DATA__: {'есть' if '__NEXT_DATA__' in text else 'нет'}")
    with open("debug_search.html", "w", encoding="utf-8") as f:
        f.write(text)
    products = extract_products(text)
    print(f"Найдено продуктов: {len(products)}")
    for p in products[:15]:
        print(f"  • {p.name} | {p.classification} | база {p.base_uah} → {p.final_uah} грн | "
              f"PS Plus: {p.in_plus} | фото: {'да' if p.image else 'нет'}")
    if not products:
        print("\nНичего не разобрал. Начало страницы:")
        print(text[:1500])


if __name__ == "__main__":
    asyncio.run(main(" ".join(sys.argv[1:]) or "Tekken 8"))
