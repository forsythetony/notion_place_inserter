"""Unit tests for table format logging utility."""

from app.pipeline_lib.table_format import format_table_log


def test_format_table_log_returns_rendered_string():
    """format_table_log returns a non-empty string with table structure."""
    result = format_table_log(
        "Test Table",
        ["ColA", "ColB"],
        [["a1", "b1"], ["a2", "b2"]],
    )
    assert isinstance(result, str)
    assert len(result) > 0
    assert "Test Table" in result
    assert "ColA" in result
    assert "ColB" in result
    assert "a1" in result
    assert "b1" in result
    assert "a2" in result
    assert "b2" in result


def test_format_table_log_single_row():
    """format_table_log handles single-row tables."""
    result = format_table_log(
        "Single Row",
        ["Key", "Value"],
        [["data_source_id", "ds-123"]],
    )
    assert "Single Row" in result
    assert "data_source_id" in result
    assert "ds-123" in result


def test_format_table_log_empty_rows():
    """format_table_log handles empty rows (headers only)."""
    result = format_table_log("Empty", ["A", "B"], [])
    assert "Empty" in result
    assert "A" in result
    assert "B" in result
