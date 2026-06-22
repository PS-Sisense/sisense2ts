-- Sample ECommerce data layer for the Sisense -> ThoughtSpot demo (Databricks).
-- Schema mirrors the live Sisense "Sample ECommerce" model extracted via A1.
-- Run in a Databricks SQL warehouse or notebook. Adjust the catalog if not using `main`.
-- Note: physical table names drop the ".csv" suffix from Sisense table ids; the converter
-- (WS-B) normalizes SourceTable.id "Country.csv" -> db_table "Country".

CREATE SCHEMA IF NOT EXISTS main.sisense_demo;
USE main.sisense_demo;

CREATE OR REPLACE TABLE Country (`Country` STRING, `Country ID` INT);
INSERT INTO Country (`Country`, `Country ID`) VALUES
  ('United States', 1), ('United Kingdom', 2), ('Canada', 3), ('Germany', 4), ('France', 5);

CREATE OR REPLACE TABLE Brand (`Brand` STRING, `Brand ID` INT);
INSERT INTO Brand (`Brand`, `Brand ID`) VALUES
  ('Acme', 1), ('Globex', 2), ('Initech', 3), ('Umbrella', 4), ('Stark', 5);

CREATE OR REPLACE TABLE Category (`Category` STRING, `Category ID` INT);
INSERT INTO Category (`Category`, `Category ID`) VALUES
  ('Apparel', 1), ('Electronics', 2), ('Home', 3), ('Toys', 4), ('Sports', 5);

CREATE OR REPLACE TABLE Commerce (
  `Age Range` STRING, `Cost` DECIMAL(18,2), `Brand ID` INT, `Category ID` INT,
  `Condition` STRING, `Country ID` INT, `Date` TIMESTAMP, `Gender` STRING,
  `Quantity` INT, `Revenue` DECIMAL(18,2), `Visit ID` INT
);
INSERT INTO Commerce (`Age Range`,`Cost`,`Brand ID`,`Category ID`,`Condition`,`Country ID`,`Date`,`Gender`,`Quantity`,`Revenue`,`Visit ID`) VALUES
  ('18-24',  50.00, 1, 1, 'New',          1, TIMESTAMP'2024-01-10', 'Female', 3, 150.00, 1001),
  ('25-34', 120.00, 2, 2, 'New',          2, TIMESTAMP'2024-02-14', 'Male',   1, 220.00, 1002),
  ('35-44',  80.00, 3, 3, 'Used',         3, TIMESTAMP'2024-03-05', 'Female', 2, 160.00, 1003),
  ('45-54', 200.00, 4, 2, 'New',          1, TIMESTAMP'2024-03-22', 'Male',   1, 350.00, 1004),
  ('55-64',  60.00, 5, 4, 'Refurbished',  4, TIMESTAMP'2024-04-02', 'Female', 4, 240.00, 1005),
  ('25-34',  90.00, 1, 5, 'New',          5, TIMESTAMP'2024-04-18', 'Male',   2, 200.00, 1006),
  ('18-24',  45.00, 2, 1, 'New',          2, TIMESTAMP'2024-05-09', 'Female', 5, 225.00, 1007),
  ('35-44', 300.00, 3, 2, 'New',          3, TIMESTAMP'2024-05-25', 'Male',   1, 480.00, 1008),
  ('45-54',  75.00, 4, 3, 'Used',         1, TIMESTAMP'2024-06-11', 'Female', 3, 240.00, 1009),
  ('25-34', 130.00, 5, 2, 'New',          4, TIMESTAMP'2024-06-30', 'Male',   2, 320.00, 1010),
  ('55-64',  55.00, 1, 4, 'New',          5, TIMESTAMP'2024-07-14', 'Female', 2, 140.00, 1011),
  ('35-44', 160.00, 2, 5, 'Refurbished',  2, TIMESTAMP'2024-07-28', 'Male',   1, 260.00, 1012),
  ('18-24',  40.00, 3, 1, 'New',          3, TIMESTAMP'2024-08-15', 'Female', 4, 200.00, 1013),
  ('45-54', 220.00, 4, 2, 'New',          1, TIMESTAMP'2024-08-30', 'Male',   1, 400.00, 1014),
  ('25-34',  95.00, 5, 3, 'Used',         4, TIMESTAMP'2024-09-12', 'Female', 2, 210.00, 1015),
  ('35-44', 110.00, 1, 5, 'New',          5, TIMESTAMP'2024-09-27', 'Male',   3, 360.00, 1016),
  ('55-64',  70.00, 2, 4, 'New',          2, TIMESTAMP'2024-10-10', 'Female', 2, 180.00, 1017),
  ('25-34', 250.00, 3, 2, 'New',          3, TIMESTAMP'2024-10-29', 'Male',   1, 420.00, 1018),
  ('18-24',  48.00, 4, 1, 'Refurbished',  1, TIMESTAMP'2024-11-16', 'Female', 5, 260.00, 1019),
  ('45-54', 140.00, 5, 3, 'New',          4, TIMESTAMP'2024-11-30', 'Male',   2, 300.00, 1020);

-- Sanity check
SELECT 'rows' AS t, count(*) AS n FROM Commerce
UNION ALL SELECT 'revenue', sum(`Revenue`) FROM Commerce;
