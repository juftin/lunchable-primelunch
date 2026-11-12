import click


@click.command
@click.option(
    "-f",
    "--file",
    "csv_file",
    type=click.Path(exists=True, resolve_path=True),
    help="File Path of the Amazon Export",
    required=True,
)
@click.option(
    "-w",
    "--window",
    "window",
    type=click.INT,
    help="Allowable time window between Amazon transaction date and "
    "credit card transaction date",
    default=7,
)
@click.option(
    "-a",
    "--all",
    "update_all",
    is_flag=True,
    type=click.BOOL,
    help="Whether to skip the confirmation step and simply update all matched "
    "transactions",
    default=False,
)
@click.option(
    "--on-conflict",
    "on_conflict",
    type=click.Choice(["append", "prepend", "replace", "skip"]),
    help="What to do when a transaction already has notes that don't contain "
    "the Amazon items",
    default="skip",
    show_default=True,
)
@click.option(
    "-t",
    "--token",
    "access_token",
    type=click.STRING,
    help=(
        "LunchMoney Access Token - defaults to the "
        "LUNCHMONEY_ACCESS_TOKEN environment variable"
    ),
    envvar="LUNCHMONEY_ACCESS_TOKEN",
)
def primelunch(
    csv_file: str, window: int, update_all: bool, on_conflict: str, access_token: str
) -> None:
    """
    Update your Amazon LunchMoney transactions
    """
    from lunchable_primelunch.primelunch import NoteConflict, PrimeLunch

    primelunch = PrimeLunch(
        file_path=csv_file,
        time_window=window,
        access_token=access_token,
        on_conflict=NoteConflict(on_conflict),
    )
    primelunch.process_transactions(confirm=not update_all)


if __name__ == "__main__":
    primelunch()
