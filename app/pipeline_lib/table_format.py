"""Generic Rich table formatter for structured log output."""

from io import StringIO

from rich.console import Console
from rich.table import Table


def format_table_log(
    title: str,
    columns: list[str],
    rows: list[list[str]],
) -> str:
    """
    Build a Rich table and return its rendered string for use in log messages.

    Args:
        title: Table title.
        columns: Column headers.
        rows: Data rows; each row is a list of cell values (one per column).

    Returns:
        Rendered table string suitable for logger.debug/info.
    """
    table = Table(title=title)
    for col in columns:
        table.add_column(col)
    for row in rows:
        table.add_row(*[str(c) for c in row])
    buf = StringIO()
    console = Console(file=buf, force_terminal=True)
    console.print(table)
    return buf.getvalue()
