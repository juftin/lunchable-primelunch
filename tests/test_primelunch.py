"""
Test Primelunch
"""

from __future__ import annotations

import locale
from pathlib import Path
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


def test_amazon_to_df_handles_gift_card_text_in_gift_column(tmp_path: Path) -> None:
    """
    Orders partly paid with a gift card balance can have AZAD write a
    description like "Gift Card:                      $6.93" into the
    `gift` column instead of a plain number. This must not blow up the
    parse, and the value should still be extracted as a float.
    """
    locale.setlocale(locale.LC_ALL, "en_US.UTF-8")
    csv_path = tmp_path / "amazon_order_history.csv"
    csv_path.write_text(
        "order id,items,to,date,total,shipping,gift,refund,payments\n"
        "D01-1,Some Book,Vince,2026-05-16,11.99,,"
        'Gift Card:                      $6.93,,2026-05-16: $11.99;\n'
    )
    primelunch = PrimeLunch(file_path=csv_path, access_token="dummy")

    amazon_df = primelunch.amazon_to_df()

    assert amazon_df["gift"].iloc[0] == pytest.approx(6.93)
