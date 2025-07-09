-- Legg til cache-kolonner for negative split og løpsøkonomi
-- Dette skal gjøres på activities-tabellen

ALTER TABLE activities 
ADD COLUMN negative_split_percent REAL;

ALTER TABLE activities 
ADD COLUMN running_economy REAL;

-- Verifiser at kolonnene ble lagt til
PRAGMA table_info(activities); 