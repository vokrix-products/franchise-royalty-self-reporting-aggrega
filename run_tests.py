import sys

from processor import process_file


def test_csv_basic():
    data = b"Location,Reporting Period End,Gross Sales\nStore A,2025-01-31,1000"
    records = process_file(data)
    assert len(records) == 1
    record = records[0]
    assert record["title"] == "Store A"
    assert record["status"] == "Pending:warning"
    assert record["due_date"] == "2025-01-31"
    assert record["details"]["gross_sales_amount"] == "1000"


def test_csv_preamble():
    data = (
        b"Franchise Sales Report\n"
        b"Generated 2025-02-01\n\n"
        b"Location\tPeriod End\tGross Sales\n"
        b"Store B\t2025-02-28\t2500"
    )
    records = process_file(data)
    assert len(records) == 1
    record = records[0]
    assert record["title"] == "Store B"
    assert record["details"]["gross_sales_amount"] == "2500"


def test_no_delimiter_returns_empty():
    data = b"Hello world no delimiters here"
    records = process_file(data)
    assert records == []


if __name__ == "__main__":
    test_csv_basic()
    test_csv_preamble()
    test_no_delimiter_returns_empty()
    print("All tests passed")
    sys.exit(0)
