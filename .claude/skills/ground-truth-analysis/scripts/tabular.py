#!/usr/bin/env python3
"""Loading and parsing shared by the reconciliation scripts.

Spreadsheet-shaped data arrives with thousands separators, currency symbols,
parenthesised negatives, Excel date serials, zero-padded IDs and IDs that a
reader has turned into floats. Getting those wrong produces differences that
are artefacts of the loader rather than facts about the data, so every script
in this directory loads through here.

Not a CLI — import it:

    from tabular import load, to_decimal, normalise_key, money

Stdlib only. Reads CSV/TSV and basic .xlsx (shared and inline strings, date
number formats, blank rows). Numbers are parsed to Decimal, never to float, so
sums are exact and a tolerance means what it says.
"""

from __future__ import annotations

import csv
import re
import unicodedata
import zipfile
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Sequence

Row = dict[str, str]

# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #

EXCEL_EPOCH = date(1899, 12, 30)  # Excel's day 1 is 1900-01-01, with a leap bug
DATE_FMT_IDS = set(range(14, 23)) | set(range(27, 37)) | set(range(45, 48)) | set(range(50, 59))


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _col_index(ref: str) -> int:
    """'BC12' -> 54 (zero-based column index)."""
    n = 0
    for ch in ref:
        if not ch.isalpha():
            break
        n = n * 26 + (ord(ch.upper()) - 64)
    return n - 1


def load_xlsx(path: Path, sheet: str | None) -> list[list[str]]:
    """Read a worksheet into rows of strings. Dates come back as ISO strings."""
    import xml.etree.ElementTree as ET

    with zipfile.ZipFile(path) as z:
        names = z.namelist()

        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")):
                shared.append("".join(t.text or "" for t in si.iter() if _local(t.tag) == "t"))

        date_styles: set[int] = set()
        if "xl/styles.xml" in names:
            root = ET.fromstring(z.read("xl/styles.xml"))
            custom = {
                int(n.get("numFmtId", "0")): n.get("formatCode", "")
                for n in root.iter()
                if _local(n.tag) == "numFmt"
            }
            xfs = next((c for c in root if _local(c.tag) == "cellXfs"), [])
            for i, xf in enumerate(xfs):
                fmt_id = int(xf.get("numFmtId", "0"))
                code = re.sub(r'"[^"]*"|\[[^\]]*\]', "", custom.get(fmt_id, ""))
                if fmt_id in DATE_FMT_IDS or re.search(r"[ymdhs]", code):
                    date_styles.add(i)

        wb = ET.fromstring(z.read("xl/workbook.xml"))
        sheets = [s for s in wb.iter() if _local(s.tag) == "sheet"]
        rels = {}
        if "xl/_rels/workbook.xml.rels" in names:
            for rel in ET.fromstring(z.read("xl/_rels/workbook.xml.rels")):
                rels[rel.get("Id")] = rel.get("Target", "").lstrip("/")
        if not sheets:
            raise SystemExit(f"{path}: no worksheets found")
        chosen = sheets[0]
        if sheet is not None:
            match = [s for s in sheets if s.get("name") == sheet]
            if not match:
                have = ", ".join(s.get("name", "?") for s in sheets)
                raise SystemExit(f"{path}: no sheet named {sheet!r}. Sheets: {have}")
            chosen = match[0]
        rid = next((v for k, v in chosen.attrib.items() if _local(k) == "id"), None)
        target = rels.get(rid, "worksheets/sheet1.xml")
        member = target if target.startswith("xl/") else f"xl/{target}"
        if member not in names:
            member = next(n for n in names if n.startswith("xl/worksheets/"))

        rows: list[list[str]] = []
        for r in ET.fromstring(z.read(member)).iter():
            if _local(r.tag) != "row":
                continue
            cells: dict[int, str] = {}
            for c in r:
                if _local(c.tag) != "c":
                    continue
                idx = _col_index(c.get("r", "")) if c.get("r") else len(cells)
                ctype = c.get("t", "n")
                text = ""
                for child in c:
                    if _local(child.tag) == "v":
                        text = child.text or ""
                    elif _local(child.tag) == "is":
                        text = "".join(t.text or "" for t in child.iter() if _local(t.tag) == "t")
                if ctype == "s" and text:
                    text = shared[int(text)]
                elif ctype == "b" and text:
                    text = "TRUE" if text == "1" else "FALSE"
                elif ctype == "n" and text and int(c.get("s", "-1") or -1) in date_styles:
                    try:
                        serial = float(text)
                        stamp = EXCEL_EPOCH + timedelta(days=serial)
                        text = stamp.isoformat() if serial % 1 else stamp.isoformat()[:10]
                    except (ValueError, OverflowError):
                        pass
                cells[idx] = text
            width = max(cells) + 1 if cells else 0
            rows.append([cells.get(i, "") for i in range(width)])
        return rows


def load(path: Path, sheet: str | None, delimiter: str | None) -> tuple[list[str], list[Row]]:
    if path.suffix.lower() in {".xlsx", ".xlsm"}:
        raw = load_xlsx(path, sheet)
    else:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        if delimiter is None:
            head = text.split("\n", 1)[0]
            delimiter = "\t" if head.count("\t") > head.count(",") else ","
        raw = [r for r in csv.reader(text.splitlines(), delimiter=delimiter)]
    raw = [r for r in raw if any(str(c).strip() for c in r)]  # drop blank rows
    if not raw:
        raise SystemExit(f"{path}: no data rows")
    header = [str(h).strip() for h in raw[0]]
    rows = [dict(zip(header, [str(c) for c in r] + [""] * (len(header) - len(r)))) for r in raw[1:]]
    return header, rows

# --------------------------------------------------------------------------- #
# Parsing and normalising
# --------------------------------------------------------------------------- #

CURRENCY = "$€£¥₹"


def to_decimal(raw: str) -> Decimal | None:
    """Parse a spreadsheet-shaped number. Returns None if it is not one."""
    s = unicodedata.normalize("NFKC", str(raw)).strip().replace(" ", "")
    if not s:
        return None
    s = s.replace("−", "-")
    negative = s.startswith("(") and s.endswith(")")
    if negative:
        s = s[1:-1]
    for ch in CURRENCY + " ":
        s = s.replace(ch, "")
    percent = s.endswith("%")
    s = s.rstrip("%")
    if s.count(",") and s.count("."):  # 1,234.56 vs 1.234,56
        s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(,\d{3})+", s):
        s = s.replace(",", "")
    elif s.count(",") == 1 and len(s.split(",")[1]) != 3:
        s = s.replace(",", ".")
    try:
        value = Decimal(s)
    except (InvalidOperation, ValueError):
        return None
    if percent:
        value /= 100
    return -value if negative else value


def normalise_key(raw: str) -> str:
    s = unicodedata.normalize("NFKC", str(raw)).strip().replace(" ", " ")
    s = re.sub(r"\s+", " ", s).casefold()
    if re.fullmatch(r"-?\d+\.0+", s):  # 1234.0 <- an ID read as a float
        s = s.split(".")[0]
    if re.fullmatch(r"0+\d+", s):  # 00742 <- a zero-padded code
        s = s.lstrip("0")
    return s


def key_of(row: Row, keys: Sequence[str], normalise: bool) -> tuple[str, ...]:
    return tuple(normalise_key(row.get(k, "")) if normalise else str(row.get(k, "")).strip() for k in keys)

# --------------------------------------------------------------------------- #
# Column typing and comparison helpers
# --------------------------------------------------------------------------- #

def numeric_columns(cols: Iterable[str], *frames: list[Row], exclude: set[str] = frozenset()) -> list[str]:
    """Columns that parse as numbers in at least 90% of non-empty cells everywhere."""
    found = []
    for col in cols:
        if col in exclude:
            continue
        ok = True
        for rows in frames:
            filled = [r[col] for r in rows[:5000] if str(r.get(col, "")).strip()]
            if not filled or sum(to_decimal(v) is not None for v in filled) < 0.9 * len(filled):
                ok = False
                break
        if ok:
            found.append(col)
    return found


def close(a: Decimal, b: Decimal, abs_tol: Decimal, rel_tol: Decimal) -> bool:
    return abs(a - b) <= max(abs_tol, rel_tol * max(abs(a), abs(b)))

def money(x: Decimal) -> str:
    return f"{x:,.4f}".rstrip("0").rstrip(".") if x % 1 else f"{x:,.0f}"
