TRUNCATE TABLE accounts;
TRUNCATE TABLE orders;
TRUNCATE TABLE notes;

INSERT INTO accounts(owner, balance) VALUES
  ('alice', 100),
  ('bob', 100);

INSERT INTO orders(amount) VALUES
  (50),
  (150),
  (200);

INSERT INTO notes(value) VALUES
  (10);
