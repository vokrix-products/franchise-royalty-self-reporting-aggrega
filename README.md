# Franchise Royalty Self-Reporting Aggregator & Exception Alerter — Extraction Processor

Processing-only backend that ingests uploaded royalty submission documents (PDF, Excel, CSV, text) and emits normalized, structured records ready for the aggregation and exception-alerting pipeline.

## Product archetype

This is the **extraction layer** of a franchise royalty self-reporting aggregator. Franchisees upload their sales/royalty statements; this backend parses those files into a consistent schema so downstream components can aggregate totals, flag missing fields, compute extraction confidence, and alert on exceptions.

## What the poller expects as input

The upstream poller calls `process_file(file_bytes: bytes) -> list[dict]` on raw file bytes. The function auto-detects the format and returns one dictionary per extracted submission row.

Each returned record contains:

- `title`: primary entity (location/unit/franchisee name)
- `status`: always `"Pending:warning"` for newly extracted submissions
- `details`: dict of extracted fields, confidence, and missing-field flags
- `due_date`: ISO-8601 date string or `None`

Extracted fields in `details` include (whichever are present in the document):

- `reporting_period_start`, `reporting_period_end`
- `statement_number`
- `gross_sales_amount`, `net_sales_amount`, `sales_tax_amount`
- `royaltyable_sales_amount`, `deductions_amount`
- `currency`, `document_date`
- `missing_fields`: fields that could not be populated
- `extraction_confidence`: 0–1 ratio of populated expected fields

If a file contains no delimiter-bearing header row, the processor returns `[]`.

## Files

- `processor.py` — core extraction module
- `run_demo.py` — hardcoded CSV demo, exits 0 on success
- `run_tests.py` — regression tests, exits 0 on success

## Usage

```bash
pip install -r requirements.txt
python3 run_demo.py
python3 run_tests.py
```
