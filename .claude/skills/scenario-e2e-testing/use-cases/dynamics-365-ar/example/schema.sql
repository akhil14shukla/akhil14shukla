-- Stand-in for the application's real migrations. In a real project,
-- `migrate_command` in e2e.config.yaml runs the app's own migration tool instead.
CREATE TABLE customers (
    customer_no text PRIMARY KEY,
    name        text NOT NULL,
    on_hold     boolean NOT NULL DEFAULT false
);

CREATE TABLE invoices (
    id          serial PRIMARY KEY,
    invoice_no  text NOT NULL UNIQUE,
    customer_no text NOT NULL REFERENCES customers,
    currency    char(3) NOT NULL,
    amount      numeric(18,2) NOT NULL,
    open_amount numeric(18,2) NOT NULL,
    due_date    date NOT NULL,
    status      text NOT NULL DEFAULT 'open'          -- open | partially_paid | paid
);

CREATE TABLE receipts (
    id               serial PRIMARY KEY,
    receipt_no       text NOT NULL UNIQUE,
    customer_no      text REFERENCES customers,
    currency         char(3) NOT NULL,
    amount           numeric(18,2) NOT NULL,
    unapplied_amount numeric(18,2) NOT NULL,
    reference        text,
    received_on      date NOT NULL,
    status           text NOT NULL DEFAULT 'unmatched', -- unmatched | matched | partially_matched | posted | post_failed
    msd_journal      text,
    msd_voucher      text,
    post_error       text,
    posted_at        timestamptz,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE allocations (
    id         serial PRIMARY KEY,
    receipt_id int NOT NULL REFERENCES receipts,
    invoice_id int NOT NULL REFERENCES invoices,
    amount     numeric(18,2) NOT NULL,
    UNIQUE (receipt_id, invoice_id)
);

CREATE TABLE closed_periods (period text PRIMARY KEY);   -- 'YYYY-MM'
