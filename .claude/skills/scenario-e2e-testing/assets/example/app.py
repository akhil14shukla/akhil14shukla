#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["psycopg[binary]>=3.1"]
# ///
"""A deliberately small accounts-receivable service, used to prove the harness.

It does what the real thing does in miniature: record a receipt, match it to
open invoices, validate it, and post it to a Dynamics 365 Finance & Operations
style OData API (OAuth token, journal header, journal lines, post action),
retrying throttled calls. The e2e scenarios next to it exercise every branch.

Environment:
    DATABASE_URL      postgresql://... the e2e database
    MSD_BASE_URL      base URL of D365 (WireMock in tests)
    MSD_TOKEN_URL     Entra ID token endpoint (WireMock in tests)
    E2E_TEST_HOOKS=1  enables PUT /__test/clock; never set in production
    PORT              default 8000
"""

from __future__ import annotations

import datetime as dt
import decimal
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.environ["DATABASE_URL"]
MSD_BASE_URL = os.environ.get("MSD_BASE_URL", "http://localhost:8080").rstrip("/")
MSD_TOKEN_URL = os.environ.get("MSD_TOKEN_URL", MSD_BASE_URL + "/tenant/oauth2/v2.0/token")
TEST_HOOKS = os.environ.get("E2E_TEST_HOOKS") == "1"
COMPANY = "usmf"
MAX_ATTEMPTS = 3

_frozen_now: dt.datetime | None = None


def now() -> dt.datetime:
    """The only clock the app reads, so tests can pin it."""
    return _frozen_now or dt.datetime.now(dt.timezone.utc)


class HttpError(Exception):
    def __init__(self, status: int, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.status, self.payload = status, {"error": message, **extra}


class MsdError(Exception):
    """D365 rejected or could not take the posting."""


# --------------------------------------------------------------------------- matching


def create_receipt(conn: psycopg.Connection, body: dict[str, Any]) -> dict[str, Any]:
    amount = decimal.Decimal(str(body["amount"]))
    if amount <= 0:
        raise HttpError(422, "amount must be positive")
    try:
        row = conn.execute(
            """INSERT INTO receipts (receipt_no, customer_no, currency, amount, unapplied_amount, reference, received_on)
               VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id, status""",
            (body["receipt_no"], body.get("customer_no"), body["currency"], amount, amount, body.get("reference"), body["received_on"]),
        ).fetchone()
    except psycopg.errors.UniqueViolation:
        raise HttpError(409, "duplicate receipt_no") from None
    return {"id": row["id"], "status": row["status"]}


def match_receipt(conn: psycopg.Connection, receipt_id: int) -> dict[str, Any]:
    receipt = conn.execute("SELECT * FROM receipts WHERE id = %s FOR UPDATE", (receipt_id,)).fetchone()
    if receipt is None:
        raise HttpError(404, "receipt not found")
    if receipt["status"] != "unmatched":
        raise HttpError(409, f"receipt is {receipt['status']}")
    invoices = conn.execute(
        """SELECT * FROM invoices WHERE customer_no = %s AND currency = %s AND open_amount > 0
           ORDER BY due_date, invoice_no FOR UPDATE""",
        (receipt["customer_no"], receipt["currency"]),
    ).fetchall()
    by_reference = [i for i in invoices if receipt["reference"] and i["invoice_no"] in receipt["reference"]]
    if by_reference:
        targets = by_reference
    elif invoices and sum(i["open_amount"] for i in invoices) == receipt["amount"]:
        targets = invoices
    else:
        targets = []

    remaining = receipt["amount"]
    for inv in targets:
        applied = min(remaining, inv["open_amount"])
        if applied <= 0:
            break
        conn.execute("INSERT INTO allocations (receipt_id, invoice_id, amount) VALUES (%s, %s, %s)", (receipt_id, inv["id"], applied))
        open_after = inv["open_amount"] - applied
        conn.execute(
            "UPDATE invoices SET open_amount = %s, status = %s WHERE id = %s",
            (open_after, "paid" if open_after == 0 else "partially_paid", inv["id"]),
        )
        remaining -= applied
    status = "unmatched" if remaining == receipt["amount"] else ("matched" if remaining == 0 else "partially_matched")
    conn.execute(
        "UPDATE receipts SET unapplied_amount = %s, status = %s, updated_at = %s WHERE id = %s",
        (remaining, status, now(), receipt_id),
    )
    return {"id": receipt_id, "status": status, "unapplied_amount": str(remaining)}


# --------------------------------------------------------------------------- posting


def post_receipt(conn: psycopg.Connection, receipt_id: int) -> dict[str, Any]:
    receipt = conn.execute(
        "SELECT r.*, c.on_hold FROM receipts r LEFT JOIN customers c USING (customer_no) WHERE r.id = %s FOR UPDATE OF r",
        (receipt_id,),
    ).fetchone()
    if receipt is None:
        raise HttpError(404, "receipt not found")
    if receipt["status"] == "posted":
        raise HttpError(409, "receipt already posted", voucher=receipt["msd_voucher"])
    if receipt["status"] not in ("matched", "partially_matched", "post_failed"):
        raise HttpError(422, f"receipt is {receipt['status']}, only matched receipts can be posted")
    if receipt["on_hold"]:
        raise HttpError(422, "customer is on hold")
    period = now().strftime("%Y-%m")
    if conn.execute("SELECT 1 FROM closed_periods WHERE period = %s", (period,)).fetchone():
        raise HttpError(422, f"posting period {period} is closed")

    allocations = conn.execute(
        """SELECT a.amount, i.invoice_no FROM allocations a JOIN invoices i ON i.id = a.invoice_id
           WHERE a.receipt_id = %s ORDER BY i.invoice_no""",
        (receipt_id,),
    ).fetchall()
    try:
        journal, voucher = send_to_msd(receipt, allocations)
    except MsdError as exc:
        conn.execute(
            "UPDATE receipts SET status = 'post_failed', post_error = %s, updated_at = %s WHERE id = %s",
            (str(exc), now(), receipt_id),
        )
        conn.commit()
        raise HttpError(502, "posting to Dynamics failed", detail=str(exc)) from exc
    conn.execute(
        """UPDATE receipts SET status = 'posted', msd_journal = %s, msd_voucher = %s, post_error = NULL,
           posted_at = %s, updated_at = %s WHERE id = %s""",
        (journal, voucher, now(), now(), receipt_id),
    )
    return {"id": receipt_id, "status": "posted", "journal": journal, "voucher": voucher}


def send_to_msd(receipt: dict[str, Any], allocations: list[dict[str, Any]]) -> tuple[str, str]:
    token = msd_token()
    trans_date = now().date().isoformat()
    header = msd_call("POST", "/data/CustomerPaymentJournalHeaders", token, {
        "dataAreaId": COMPANY, "JournalName": "CustPay", "Description": f"Receipt {receipt['receipt_no']}",
    })
    batch = header["JournalBatchNumber"]
    lines = [{"MarkedInvoice": a["invoice_no"], "CreditAmount": float(a["amount"])} for a in allocations]
    if receipt["unapplied_amount"] > 0:
        lines.append({"MarkedInvoice": "", "CreditAmount": float(receipt["unapplied_amount"])})  # on-account
    for line in lines:
        msd_call("POST", "/data/CustomerPaymentJournalLines", token, {
            "dataAreaId": COMPANY, "JournalBatchNumber": batch, "AccountType": "Cust",
            "AccountDisplayValue": receipt["customer_no"], "CurrencyCode": receipt["currency"],
            "TransDate": trans_date, "PaymentReference": receipt["receipt_no"], **line,
        })
    posted = msd_call("POST", "/api/services/ARIntegrationServices/ARPostingService/postJournal", token, {
        "_dataAreaId": COMPANY, "_journalBatchNumber": batch,
    })
    return batch, posted["Voucher"]


def msd_token() -> str:
    form = urllib.parse.urlencode({
        "grant_type": "client_credentials", "client_id": "e2e", "client_secret": "e2e",
        "scope": MSD_BASE_URL + "/.default",
    }).encode()
    status, body, _ = raw_call("POST", MSD_TOKEN_URL, form, {"Content-Type": "application/x-www-form-urlencoded"})
    if status != 200:
        raise MsdError(f"token request failed with HTTP {status}")
    return body["access_token"]


def msd_call(method: str, path: str, token: str, payload: dict[str, Any]) -> dict[str, Any]:
    """One OData call with retry on throttling (429) and transient 503, honouring Retry-After."""
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    for attempt in range(1, MAX_ATTEMPTS + 1):
        status, body, retry_after = raw_call(method, MSD_BASE_URL + path, json.dumps(payload).encode(), headers)
        if status in (429, 503) and attempt < MAX_ATTEMPTS:
            time.sleep(min(float(retry_after or 1), 2.0))
            continue
        if status >= 400:
            message = (body or {}).get("error", {}).get("message") if isinstance(body, dict) else None
            raise MsdError(f"{path} HTTP {status}: {message or 'no error message'}")
        return body or {}
    raise AssertionError("unreachable")


def raw_call(method: str, url: str, data: bytes, headers: dict[str, str]) -> tuple[int, Any, str | None]:
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            status, raw, retry_after = resp.status, resp.read(), resp.headers.get("Retry-After")
    except urllib.error.HTTPError as err:
        status, raw, retry_after = err.code, err.read(), err.headers.get("Retry-After")
    except OSError as exc:
        raise MsdError(f"{url} unreachable: {exc}") from exc
    try:
        return status, json.loads(raw) if raw else None, retry_after
    except json.JSONDecodeError:
        return status, None, retry_after


# --------------------------------------------------------------------------- http


ROUTES = [
    ("POST", re.compile(r"^/receipts$"), lambda c, b, m: (201, create_receipt(c, b))),
    ("POST", re.compile(r"^/receipts/(\d+)/match$"), lambda c, b, m: (200, match_receipt(c, int(m[1])))),
    ("POST", re.compile(r"^/receipts/(\d+)/post$"), lambda c, b, m: (200, post_receipt(c, int(m[1])))),
]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/health":
            self.reply(200, {"ok": True})
        else:
            self.reply(404, {"error": "not found"})

    def do_PUT(self) -> None:
        global _frozen_now
        if TEST_HOOKS and self.path == "/__test/clock":
            _frozen_now = dt.datetime.fromisoformat(self.body()["now"].replace("Z", "+00:00"))
            self.reply(204, None)
        else:
            self.reply(404, {"error": "not found"})

    def do_POST(self) -> None:
        for method, pattern, handler in ROUTES:
            if method == "POST" and (m := pattern.match(self.path)):
                try:
                    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
                        status, payload = handler(conn, self.body(), m)
                    self.reply(status, payload)
                except HttpError as exc:
                    self.reply(exc.status, exc.payload)
                return
        self.reply(404, {"error": "not found"})

    def body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length)) if length else {}

    def reply(self, status: int, payload: Any) -> None:
        data = b"" if payload is None else json.dumps(payload, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args: Any) -> None:
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8000"))), Handler).serve_forever()  # noqa: S104
