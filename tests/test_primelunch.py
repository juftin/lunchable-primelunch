"""
Test Primelunch
"""

from __future__ import annotations

import locale
from typing import TypedDict

import pytest

from lunchable_primelunch.primelunch import PrimeLunch


class CurrencyConversion(TypedDict):
    currency: str
    amount: float
    locale_name: str


CURRENCY_CONVERSIONS: list[CurrencyConversion] = [
    {"currency": "$1,234", "amount": 1234.0, "locale_name": "en_US.UTF-8"},
    {"currency": "€1234,00", "amount": 1234.0, "locale_name": "de_DE.UTF-8"},
    {"currency": "£1,234.12", "amount": 1234.12, "locale_name": "en_GB.UTF-8"},
    {"currency": "23", "amount": 23.0, "locale_name": "en_US.UTF-8"},
    {"currency": "23", "amount": 23.0, "locale_name": "en_GB.UTF-8"},
    {"currency": "23,00", "amount": 23.0, "locale_name": "de_DE.UTF-8"},
    {"currency": "₽50,00", "amount": 50.0, "locale_name": "ru_RU.UTF-8"},
    {"currency": "€12.345,67", "amount": 12345.67, "locale_name": "de_DE.UTF-8"},
]


@pytest.mark.parametrize("conversion", CURRENCY_CONVERSIONS)
def test_currency_str(conversion: CurrencyConversion) -> None:
    """
    Test the currency string conversion to float.
    """
    locale.setlocale(locale.LC_ALL, conversion["locale_name"])
    assert PrimeLunch.currency_to_float(conversion["currency"]) == conversion["amount"]
