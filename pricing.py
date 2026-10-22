"""Курсы GameCentr: перевод цены PS Store (UAH) в UZS и прайс PS Plus."""

# (минимальная цена в гривнах, курс UZS за 1 гривну), по возрастанию
UAH_TIERS = [
    (249, 430),
    (300, 390),
    (700, 370),
    (1100, 360),
    (1500, 350),
    (2000, 340),
    (2900, 330),
]


def uah_rate(uah: float) -> int:
    """Курс для указанной цены. Ниже 249 грн берём первый курс, выше 5000 — последний."""
    rate = UAH_TIERS[0][1]
    for threshold, tier_rate in UAH_TIERS:
        if uah >= threshold:
            rate = tier_rate
    return rate


def uah_to_uzs(uah: float) -> int:
    return round(uah * uah_rate(uah))


def fmt_uzs(amount: int) -> str:
    return f"{amount:,}".replace(",", " ") + " UZS"


PS_PLUS_TEXT = """🎮 <b>PS Plus Deluxe</b>
• 12 месяцев — 849 000 UZS
• 3 месяца — 449 000 UZS
• 1 месяц — 199 000 UZS

🎮 <b>PS Plus Extra</b>
• 12 месяцев — 749 000 UZS
• 3 месяца — 389 000 UZS
• 1 месяц — 179 000 UZS

🎮 <b>PS Plus Essential</b>
• 12 месяцев — 499 000 UZS
• 3 месяца — 249 000 UZS
• 1 месяц — 149 000 UZS

🔥 <b>EA Play</b>
• 12 месяцев — 349 000 UZS
• 1 месяц — 99 000 UZS"""
