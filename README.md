# gamecentr-bot

Telegram-бот GameCentr: отправляете название игры — бот находит её в
[PS Store Украина](https://store.playstation.com/ru-ua/pages/latest), считает цену в UZS
по курсу и присылает название, цену и обложку.

**Какое издание берётся:**
- если у игры есть скидка — самое дешёвое издание по акции;
- если скидок нет — самое полное (самое дорогое) издание: Deluxe / Ultimate и т.п.

Скидки только для подписчиков PS Plus не учитываются. Курсы и прайс PS Plus — в `pricing.py`.

Команды: `/start`, `/psplus` — прайс подписок PS Plus и EA Play.

## Запуск

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # и впишите туда BOT_TOKEN
python bot.py
```

Бот должен работать на компьютере или сервере, которому доступны store.playstation.com
и api.telegram.org.
