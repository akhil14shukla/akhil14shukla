-- Reference data every scenario shares. Keep it small and boring: anything a
-- scenario's outcome depends on belongs in that scenario's own `given`.
INSERT INTO customers (customer_no, name, on_hold) VALUES
    ('C001', 'Contoso Retail',  false),
    ('C002', 'Fabrikam Supply', false),
    ('C900', 'Litware (credit hold)', true);
