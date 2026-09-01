import csv
import io
import re
from datetime import datetime
from typing import Any, Optional

import pdfplumber
import openpyxl

STATUS_PENDING = "Pending:warning"

FIELD_TOKEN_MAP = {
    "title": [
        "location", "unit", "store", "franchisee", "restaurant",
        "venue", "shop", "name", "code", "location name",
        "unit name", "store name", "franchisee name"
    ],
    "reporting_period_start": [
        "start date", "period start", "start", "period from", "from date"
    ],
    "reporting_period_end": [
        "end date", "period end", "end", "period to", "to date"
    ],
    "statement_number": [
        "statement no", "report no", "statement number", "report number",
        "document no", "invoice no", "reference", "doc no", "receipt no"
    ],
    "gross_sales_amount": [
        "gross sales", "gross amount", "gross", "total sales",
        "sales amount", "revenue", "gross revenue"
    ],
    "net_sales_amount": [
        "net sales", "net amount", "net", "net revenue"
    ],
    "sales_tax_amount": [
        "sales tax", "tax amount", "gst", "vat", "hst", "tax"
    ],
    "royaltyable_sales_amount": [
        "royaltyable sales", "royalty sales", "royalty base",
        "royaltyable", "royalty"
    ],
    "deductions_amount": [
        "deductions", "exclusions", "adjustments", "comps",
        "discounts", "returns", "credits"
    ],
    "currency": [
        "currency", "cur", "money"
    ],
    "document_date": [
        "document date", "doc date", "date", "invoice date",
        "statement date"
    ],
}


def _normalize_key(value: str) -> str:
    if not value:
        return ""
    value = value.lower()
    value = re.sub(r"[^a-z0-9 ]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _parse_date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None

    formats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%m-%d-%Y",
        "%d-%m-%Y",
        "%Y/%m/%d",
        "%b %d, %Y",
        "%B %d, %Y",
        "%d %b %Y",
        "%d %B %Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    match = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    if match:
        return match.group(1)
    return None


def _find_header_row_index(rows: list[list[str]]) -> int:
    for i, row in enumerate(rows):
        non_empty = [c for c in row if c and str(c).strip()]
        if len(non_empty) >= 2 and any(re.search(r"[A-Za-z]", str(c)) for c in non_empty):
            return i
    return 0


def _confidence(col_map: dict[str, int], row: list[str]) -> float:
    present = 0
    total = 0
    for field in FIELD_TOKEN_MAP:
        if field == "title":
            continue
        total += 1
        idx = col_map.get(field)
        if idx is not None and idx < len(row) and row[idx] and str(row[idx]).strip():
            present += 1
    return round(present / total, 2) if total else 1.0


def _parse_tabular_data(rows: list[list[str]]) -> list[dict]:
    if not rows or len(rows) < 2:
        return []

    header = [str(c).strip() if c is not None else "" for c in rows[0]]
    col_map: dict[str, int] = {}

    for idx, raw_header in enumerate(header):
        nh = _normalize_key(raw_header)
        for field, tokens in FIELD_TOKEN_MAP.items():
            if any(token in nh for token in tokens):
                if field not in col_map:
                    col_map[field] = idx
                break

    title_idx = col_map.get("title")
    if title_idx is None:
        return []

    records = []
    for row in rows[1:]:
        if not row or all(c is None or str(c).strip() == "" for c in row):
            continue

        title = str(row[title_idx]).strip() if title_idx < len(row) and row[title_idx] is not None else ""
        if not title:
            continue

        details: dict[str, Any] = {}
        for field, idx in col_map.items():
            if field == "title":
                continue
            value = ""
            if idx < len(row) and row[idx] is not None:
                value = str(row[idx]).strip()
            if value:
                details[field] = value

        missing_fields = []
        for field, idx in col_map.items():
            if field == "title":
                continue
            if idx >= len(row) or row[idx] is None or str(row[idx]).strip() == "":
                missing_fields.append(field)
        for field in FIELD_TOKEN_MAP:
            if field != "title" and field not in col_map:
                missing_fields.append(field)

        details["missing_fields"] = sorted(set(missing_fields))
        details["extraction_confidence"] = _confidence(col_map, row)

        end_date_value = details.get("reporting_period_end") or details.get("document_date")
        due_date = _parse_date(end_date_value)

        records.append({
            "title": title,
            "status": STATUS_PENDING,
            "details": details,
            "due_date": due_date,
        })

    return records


def _parse_text_to_records(text: str) -> list[dict]:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return []

    delimiter = None
    for line in lines:
        for candidate in (",", "\t", ";"):
            if candidate in line:
                delimiter = candidate
                break
        if delimiter:
            break

    if not delimiter:
        return []

    header_idx = None
    for i, line in enumerate(lines):
        if delimiter in line:
            header_idx = i
            break

    if header_idx is None:
        return []

    sample = "\n".join(lines[header_idx:])
    reader = csv.reader(io.StringIO(sample), delimiter=delimiter)
    rows = list(reader)
    return _parse_tabular_data(rows)


def process_file(file_bytes: bytes) -> list[dict]:
    records: list[dict] = []

    # 1) PDF first
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                table = page.extract_table()
                if table:
                    table_rows = [
                        [str(c).strip() if c is not None else "" for c in row]
                        for row in table
                        if any(c is not None for c in row)
                    ]
                    if table_rows:
                        header_idx = _find_header_row_index(table_rows)
                        records.extend(_parse_tabular_data(table_rows[header_idx:]))
                else:
                    page_text = page.extract_text() or ""
                    if page_text:
                        records.extend(_parse_text_to_records(page_text))
        if records:
            return records
    except Exception:
        pass

    # 2) Excel
    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        for ws in wb.worksheets:
            excel_rows = []
            for row in ws.iter_rows(values_only=True):
                if any(c is not None for c in row):
                    excel_rows.append([str(c).strip() if c is not None else "" for c in row])
            if excel_rows:
                header_idx = _find_header_row_index(excel_rows)
                records.extend(_parse_tabular_data(excel_rows[header_idx:]))
        if records:
            return records
    except Exception:
        pass

    # 3) UTF-8 text / CSV fallback
    try:
        text = file_bytes.decode("utf-8", errors="ignore")
    except Exception:
        text = ""
    if text:
        records.extend(_parse_text_to_records(text))

    return records
