"""Курсы GameCentr: перевод цены PS Store (UAH) в UZS и прайс PS Plus."""

from __future__ import annotations

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


# Та же таблица в виде диапазонов «от — до», как в прайсе. Нужна для самопроверки.
UAH_RANGES = [
    (249, 299, 430),
    (300, 699, 390),
    (700, 1099, 370),
    (1100, 1499, 360),
    (1500, 1999, 350),
    (2000, 2899, 340),
    (2900, 5000, 330),
]


def _rate_by_ranges(uah: float) -> int:
    if uah < UAH_RANGES[0][0]:
        return UAH_RANGES[0][2]
    if uah > UAH_RANGES[-1][1]:
        return UAH_RANGES[-1][2]
    for lo, hi, rate in UAH_RANGES:
        if lo <= uah < hi + 1:  # +1: дробные цены вроде 299,50 остаются в своём диапазоне
            return rate
    raise ValueError(f"Цена {uah} грн не попала ни в один диапазон")


def uah_to_uzs(uah: float) -> int:
    rate = uah_rate(uah)
    check = _rate_by_ranges(uah)
    if rate != check:
        raise ValueError(f"Расхождение курса для {uah} грн: {rate} != {check}")
    return round(uah * rate)


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
