"""
PrimeLunch Utils
"""

from __future__ import annotations

import datetime
import html
import logging
import os
import pathlib
from typing import Any, Iterable

import numpy as np
import pandas as pd
from lunchable.models import (
    CategoriesObject,
    LunchableModel,
    TransactionObject,
    TransactionUpdateObject,
    UserObject,
)
from lunchable.plugins import LunchableApp, LunchableModelType
from numpy import datetime64
from rich import print, table
from rich.prompt import Confirm

logger = logging.getLogger(__name__)


class PrimeLunch(LunchableApp):
    """
    PrimeLunch: Amazon Notes Updater
    """

    def __init__(
        self,
        file_path: str | os.PathLike[str] | pathlib.Path,
        time_window: int = 7,
        access_token: str | None = None,
    ) -> None:
        """
        Initialize and set internal data
        """
        super().__init__(access_token=access_token)
        self.file_path = pathlib.Path(file_path)
        self.time_window = time_window

    @staticmethod
    def models_to_df(models: Iterable[LunchableModel]) -> pd.DataFrame:
        """
        Convert Transactions Array to DataFrame

        Parameters
        ----------
        models: List[LunchableModel]

        Returns
        -------
        pd.DataFrame
        """
        if not isinstance(models, list):
            models = list(models)
        return pd.DataFrame(
            [item.model_dump() for item in models],
            columns=models[0].model_fields.keys(),
        )

    @staticmethod
    def df_to_models(
        df: pd.DataFrame, model_type: type[LunchableModelType]
    ) -> list[LunchableModelType]:
        """
        Convert DataFrame to Transaction Array

        Parameters
        ----------
        df: pd.DataFrame
        model_type: Type[LunchableModel]

        Returns
        -------
        List[LunchableModel]
        """
        array_df = df.copy()
        array_df = array_df.replace(np.NaN, None)
        model_array = array_df.to_dict(orient="records")
        return [model_type.model_validate(item) for item in model_array]

    def _remove_subtotal_row(self, amazon_df: pd.DataFrame) -> pd.DataFrame:
        """
        Inspect the last row of the dataframe and delete it if any of its values
        contain the string "=SUBTOTAL".

        Parameters
        ----------
        amazon_df : pd.DataFrame
            The dataframe to inspect and potentially modify.

        Returns
        -------
        pd.DataFrame
            The potentially modified dataframe.
        """
        if amazon_df.iloc[-1].astype(str).str.contains("=SUBTOTAL").any():
            amazon_df = amazon_df[:-1]
        return amazon_df

    def amazon_to_df(self) -> pd.DataFrame:
        """
        Read an Amazon Data File to a DataFrame

        This is pretty simple, except duplicate header rows need to be cleaned
        If the exporter included a "subtotal" row, it is removed

        Returns
        -------
        pd.DataFrame
        """
        dt64: np.dtype[datetime64] = np.dtype("datetime64[ns]")
        expected_columns = {
            "order id": str,
            "items": str,
            "to": str,
            "date": dt64,
            "total": np.float64,
            "shipping": np.float64,
            "gift": np.float64,
            "refund": np.float64,
            "payments": str,
        }
        amazon_df = pd.read_csv(
            self.file_path,
            usecols=expected_columns.keys(),
        )
        header_row_eval = pd.concat(
            [amazon_df[item] == item for item in expected_columns.keys()], axis=1
        ).all(axis=1)
        duplicate_header_rows = np.where(header_row_eval)[0]
        amazon_df.drop(duplicate_header_rows, axis=0, inplace=True)

        amazon_df = self._remove_subtotal_row(amazon_df)

        amazon_df["total"] = (
            amazon_df["total"].astype("string").str.replace(",", "").astype(np.float64)
        )
        amazon_df = amazon_df.astype(dtype=expected_columns, copy=True, errors="raise")
        logger.info("Amazon Data File loaded: %s", self.file_path)
        return amazon_df

    @classmethod
    def filter_amazon_transactions(cls, df: pd.DataFrame) -> pd.DataFrame:
        """
        Filter a DataFrame to Amazon Transactions

        Parameters
        ----------
        df: pd.DataFrame

        Returns
        -------
        pd.DataFrame
        """
        amazon_transactions = df.copy()
        amazon_transactions["original_name"] = amazon_transactions[
            "original_name"
        ].fillna("")
        amazon_transactions = amazon_transactions[
            amazon_transactions.payee.str.match(
                r"(?i)(Amazon|AMZN|Whole Foods)(\s?(Prime|Marketplace|MKTP)|\.\w+)?",
                case=False,
            )
            | amazon_transactions.original_name.str.match(
                r"(?i)(Amazon|AMZN|Whole Foods)(\s?(Prime|Marketplace|MKTP)|\.\w+)?",
                case=False,
            )
        ]
        return amazon_transactions

    @classmethod
    def deduplicate_matched(cls, df: pd.DataFrame) -> pd.DataFrame:
        """
        Deduplicate Multiple Connections Made

        Parameters
        ----------
        df: pd.DataFrame

        Returns
        -------
        pd.DataFrame
        """
        deduped = df.copy()
        deduped["duplicated"] = deduped.duplicated(subset=["id"], keep=False)
        deduped = deduped[deduped["duplicated"] == False]  # noqa:E712
        return deduped

    @classmethod
    def _extract_total_from_payments(cls, df: pd.DataFrame) -> pd.DataFrame:
        """
        Extract the Credit Card Payments from the payments column

        There is quite a bit of data manipulation going on here. We
        need to extract meaningful credit card transaction info from strings like this:

        Visa ending in 9470: September 11, 2022: $29.57; \
        Visa ending in 9470: September 11, 2022: $2.22;
        """
        extracted = df.copy()
        extracted["new_total"] = extracted["payments"].str.rstrip(";").str.split(";")
        exploded_totals = extracted.explode("new_total", ignore_index=True)
        exploded_totals = exploded_totals[
            exploded_totals["new_total"].str.strip() != ""
        ]
        currency_matcher = r"(?:[\£\$\€]{1}[,\d]+.?\d*)"
        exploded_totals["parsed_total"] = exploded_totals["new_total"].str.findall(
            currency_matcher
        )
        exploded_totals = exploded_totals.explode("parsed_total", ignore_index=True)
        exploded_totals["parsed_total"] = exploded_totals["parsed_total"].str.replace(
            "[^0-9.]", "", regex=True
        )
        exploded_totals["parsed_total"] = exploded_totals["parsed_total"].astype(
            np.float64
        )
        exploded_totals = exploded_totals[~exploded_totals["parsed_total"].isnull()]
        exploded_totals["total"] = np.where(
            ~exploded_totals["parsed_total"].isnull(),
            exploded_totals["parsed_total"],
            exploded_totals["total"],
        )
        return exploded_totals

    @classmethod
    def _extract_extra_from_orders(cls, df: pd.DataFrame) -> pd.DataFrame:
        """
        Extract the Credit Card Refunds and Whole Foods Orders
        """
        refunds = df.copy()
        refunded_data = refunds[refunds["refund"] > 0].copy()
        refunded_data["total"] = -refunded_data["refund"]
        refunded_data["items"] = "REFUND: " + refunded_data["items"]
        complete_amazon_data = pd.concat([refunds, refunded_data], ignore_index=True)
        complete_amazon_data["items"] = np.where(
            complete_amazon_data["to"].str.startswith("Whole Foods"),
            "Whole Foods Groceries",
            complete_amazon_data["items"],
        )
        return complete_amazon_data

    @classmethod
    def merge_transactions(
        cls, amazon: pd.DataFrame, transactions: pd.DataFrame, time_range: int = 7
    ) -> pd.DataFrame:
        """
        Merge Amazon Transactions and LunchMoney Transaction

        Parameters
        ----------
        amazon: pd.DataFrame
        transactions: pd.DataFrame
        time_range: int
            Number of days used to connect credit card transactions with
            Amazon transactions

        Returns
        -------
        pd.DataFrame
        """
        exploded_totals = cls._extract_total_from_payments(df=amazon)
        complete_amazon_data = cls._extract_extra_from_orders(df=exploded_totals)
        merged_data = transactions.copy()
        merged_data = merged_data.merge(
            complete_amazon_data,
            how="inner",
            left_on=["amount"],
            right_on=["total"],
            suffixes=(None, "_amazon"),
        )
        merged_data["start_date"] = merged_data["date_amazon"]
        merged_data["end_date"] = merged_data["date_amazon"] + datetime.timedelta(
            days=time_range
        )
        merged_data.query(
            "start_date <= date <= end_date",
            inplace=True,
        )
        merged_data["notes"] = merged_data["items"]
        deduplicated = cls.deduplicate_matched(df=merged_data)
        logger.info("%s Matching Amazon Transactions Identified", len(deduplicated))
        return deduplicated[TransactionObject.__fields__.keys()]

    def cache_transactions(
        self, start_date: datetime.date, end_date: datetime.date
    ) -> dict[int, TransactionObject]:
        """
        Cache Transactions to Memory

        Parameters
        ----------
        start_date : datetime.date
        end_date : datetime.date

        Returns
        -------
        Dict[int, TransactionObject]
        """
        end_cache_date = end_date + datetime.timedelta(days=self.time_window)
        logger.info(
            "Fetching LunchMoney transactions between %s and %s",
            start_date,
            end_cache_date,
        )
        self.refresh_data(models=[UserObject, CategoriesObject])
        self.refresh_transactions(start_date=start_date, end_date=end_cache_date)
        logger.info(
            'Scanning LunchMoney Budget: "%s"',
            html.unescape(self.data.user.budget_name),
        )
        logger.info(
            "%s transactions returned from LunchMoney",
            len(self.data.transactions),
        )
        return self.data.transactions

    def print_transaction(
        self, transaction: TransactionObject, former_transaction: TransactionObject
    ) -> None:
        """
        Print a Transaction for interactive input
        """
        transaction_table = table.Table(show_header=False)
        notes_table = table.Table(show_header=False)
        transaction_table.add_row("🛒 Transaction ID", str(former_transaction.id))
        transaction_table.add_row("🏦 Payee", former_transaction.payee)
        transaction_table.add_row("📅 Date", str(former_transaction.date))
        transaction_table.add_row(
            "💰 Amount", self.format_currency(amount=former_transaction.amount)
        )
        if former_transaction.category_id is not None:
            transaction_table.add_row(
                "📊 Category",
                self.data.categories[former_transaction.category_id].name,
            )
        if (
            former_transaction.original_name is not None
            and former_transaction.original_name != former_transaction.payee
        ):
            transaction_table.add_row(
                "🏦 Original Payee", former_transaction.original_name
            )
        if former_transaction.notes is not None:
            transaction_table.add_row("📝 Notes", former_transaction.notes)
        notes_table.add_row(
            "🗒  Amazon Notes",
            transaction.notes.strip(),
        )
        print()
        print(transaction_table)
        print(notes_table)

    def update_transaction(
        self, transaction: TransactionObject, confirm: bool = True
    ) -> dict[str, Any] | None:
        """
        Update a Transaction's Notes if they've changed

        Parameters
        ----------
        transaction: TransactionObject
        confirm: bool

        Returns
        -------
        Optional[Dict[str, Any]]
        """
        former_transaction = self.data.transactions[transaction.id]
        response = None
        stripped_notes = transaction.notes.strip()
        acceptable_length = min(349, len(stripped_notes))
        new_notes = stripped_notes[:acceptable_length]
        if former_transaction.notes != new_notes:
            confirmation = True
            if confirm is True:
                self.print_transaction(
                    transaction=transaction, former_transaction=former_transaction
                )
                confirmation = Confirm.ask(
                    f"\t❓ Should we update transaction #{transaction.id}?"
                )
            if confirmation is True:
                response = self.lunch.update_transaction(
                    transaction_id=transaction.id,
                    transaction=TransactionUpdateObject(notes=new_notes),
                )
                if confirm is True:
                    print(f"\t✅ Transaction #{transaction.id} updated")
        return response

    def process_transactions(self, confirm: bool = True) -> None:
        """
        Run the End-to-End Process
        """
        logger.info(
            "Beginning search to match Amazon and LunchMoney - using %s day window",
            self.time_window,
        )
        amazon_df = self.amazon_to_df()
        min_date = amazon_df["date"].min().to_pydatetime().date()
        max_date = amazon_df["date"].max().to_pydatetime().date()
        logger.info(
            "%s Amazon transactions loaded ranging from %s to %s",
            len(amazon_df),
            min_date,
            max_date,
        )
        self.cache_transactions(start_date=min_date, end_date=max_date)
        transaction_df = self.models_to_df(
            models=self.data.transactions.values(),
        )
        amazon_transaction_df = self.filter_amazon_transactions(df=transaction_df)
        merged_data = self.merge_transactions(
            transactions=amazon_transaction_df,
            amazon=amazon_df,
            time_range=self.time_window,
        )
        updated_transactions = self.df_to_models(
            df=merged_data, model_type=TransactionObject
        )
        responses = []
        for item in updated_transactions:
            resp = self.update_transaction(transaction=item, confirm=confirm)
            if resp is not None:
                responses.append(resp)
        logger.info("%s LunchMoney transactions updated", len(responses))

    @staticmethod
    def format_currency(amount: float) -> str:
        """
        Format currency amounts to be pleasant and human readable

        Parameters
        ----------
        amount: float
            Float Amount to be converted into a string

        Returns
        -------
        str
        """
        if amount < 0:
            float_string = f"[bold red]$ ({float(abs(amount)):,.2f})[/bold red]"
        else:
            float_string = f"[bold green]$ {float(amount):,.2f}[/bold green]"
        return float_string
