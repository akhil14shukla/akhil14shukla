-- Shared by several matching scenarios: C001 owes two invoices, oldest first.
INSERT INTO invoices (invoice_no, customer_no, currency, amount, open_amount, due_date) VALUES
    ('INV-1001', 'C001', 'USD', 1000.00, 1000.00, '2026-02-28'),
    ('INV-1002', 'C001', 'USD',  250.00,  250.00, '2026-03-15');
