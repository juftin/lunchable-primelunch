"""
Regression test for PrimeLunch.df_to_models mishandling missing values.
"""

import datetime
import pathlib

from lunchable.models import TransactionObject
from pydantic import ValidationError

from lunchable_primelunch.primelunch import PrimeLunch

# A minimal, realistic Amazon order history export - the same shape/columns
# `amazon_to_df` expects from a real Amazon Order History Reporter download.
AMAZON_ORDER_HISTORY_CSV = (
    "order id,items,to,date,total,shipping,gift,refund,payments\n"
    "111-1111111-1111111,Wireless Mouse; USB-C Cable;,Jane Doe,2026-06-01,24.99,0,,,"
    "Visa ending in 1234: 2026-06-01: $24.99;\n"
    "111-2222222-2222222,Desk Lamp;,Jane Doe,2026-06-03,19.5,0,,,"
    "Visa ending in 1234: 2026-06-03: $19.50;\n"
)


def _transaction(
    txn_id: int,
    date: datetime.date,
    amount: float,
    external_id: str | None = None,
) -> TransactionObject:
    # lunchable's TransactionObject fields use positional `Field(None, ...)`
    # rather than `Field(default=None, ...)`, so mypy's dataclass-transform
    # inference treats every field as required even though pydantic treats
    # them as optional at runtime.
    return TransactionObject(  # type: ignore[call-arg]
        id=txn_id,
        date=date,
        amount=amount,
        payee="Amazon",
        original_name="AMAZON.COM",
        external_id=external_id,
    )


def test_df_to_models_returns_none_not_nan_for_matched_amazon_transactions(
    tmp_path: pathlib.Path,
) -> None:
    """
    Reproduces the real end-to-end failure from a real Amazon order history
    export, with no Lunch Money API access needed.

    The real-world failure was on `recurring_payee`, a field only present on
    newer `lunchable` releases than the one this repo's lockfile pins,
    so `external_id` stands in here - it's an equally plain optional string
    field, untouched by `primelunch.py`, that's `None` on transactions 1 and
    2 below.

    Transaction 3 (Netflix) never matches an Amazon order and is filtered
    out below by `filter_amazon_transactions` - it's only here because its
    presence in the full transaction set, alongside transactions 1 and 2
    having no external id at all, is what changes how pandas represents
    "no external id" for everyone once it's all loaded into one DataFrame
    together (a real Lunch Money account will always have some ordinary
    externally-linked transaction like this one sitting alongside one-off
    Amazon purchases that were entered manually).
    """
    csv_path = tmp_path / "amazon_order_history.csv"
    csv_path.write_text(AMAZON_ORDER_HISTORY_CSV)

    app = PrimeLunch(
        file_path=csv_path, time_window=60, access_token="fake-token-for-testing"
    )
    amazon_df = app.amazon_to_df()

    all_transactions = [
        _transaction(txn_id=1, date=datetime.date(2026, 6, 2), amount=24.99),
        _transaction(txn_id=2, date=datetime.date(2026, 6, 4), amount=19.50),
        _transaction(
            txn_id=3,
            date=datetime.date(2026, 6, 5),
            amount=15.99,
            external_id="netflix-subscription",
        ),
    ]
    app.data.transactions = {t.id: t for t in all_transactions}

    transaction_df = app.models_to_df(models=app.data.transactions.values())
    amazon_transaction_df = app.filter_amazon_transactions(df=transaction_df)
    merged_data = app.merge_transactions(
        transactions=amazon_transaction_df,
        amazon=amazon_df,
        time_range=app.time_window,
    )

    try:
        updated_transactions = app.df_to_models(
            df=merged_data, model_type=TransactionObject
        )
        raised = None
    except ValidationError as exc:
        updated_transactions = []
        raised = exc

    assert raised is None, f"df_to_models raised: {raised}"
    assert {t.id for t in updated_transactions} == {1, 2}
    assert all(t.external_id is None for t in updated_transactions)
