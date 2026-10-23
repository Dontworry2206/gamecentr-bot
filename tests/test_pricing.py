import pytest

from pricing import uah_rate, uah_to_uzs

# Каждая граница прайса: (цена в грн, ожидаемый курс)
CASES = [
    (100, 430), (249, 430), (299, 430),
    (300, 390), (699, 390),
    (700, 370), (1099, 370),
    (1100, 360), (1499, 360),
    (1500, 350), (1999, 350),
    (2000, 340), (2899, 340),
    (2900, 330), (5000, 330), (6000, 330),
]


@pytest.mark.parametrize("uah,rate", CASES)
def test_rate(uah, rate):
    assert uah_rate(uah) == rate
    assert uah_to_uzs(uah) == uah * rate


def test_examples():
    assert uah_to_uzs(1999) == 699_650
    assert uah_to_uzs(2799) == 951_660
    assert uah_to_uzs(299.5) == round(299.5 * 430)


def test_every_hryvnia_consistent():
    for uah in range(0, 7001):
        uah_to_uzs(uah)  # бросит ValueError при расхождении двух способов расчёта
