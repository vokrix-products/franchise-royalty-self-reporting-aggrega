import sys

from processor import process_file


def main() -> int:
    test_bytes = (
        b"Location,Reporting Period Start,Reporting Period End,Gross Sales,"
        b"Net Sales,Sales Tax,Deductions,Currency,Document Date\n"
        b"Downtown Cafe,2025-01-01,2025-01-31,15000.00,14000.00,1000.00,500.00,USD,2025-02-01"
    )

    results = process_file(test_bytes)

    assert isinstance(results, list)
    assert len(results) == 1

    record = results[0]
    assert record["title"] == "Downtown Cafe"
    assert record["status"] == "Pending:warning"
    assert record["due_date"] == "2025-01-31"
    assert record["details"]["gross_sales_amount"] == "15000.00"
    assert record["details"]["net_sales_amount"] == "14000.00"
    assert record["details"]["sales_tax_amount"] == "1000.00"

    print(f"Demo succeeded: {results}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
