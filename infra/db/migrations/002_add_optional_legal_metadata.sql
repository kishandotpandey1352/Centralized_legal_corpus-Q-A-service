ALTER TABLE documents ADD COLUMN IF NOT EXISTS jurisdiction TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS court TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS canonical_citation TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS decision_date DATE;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS practice_area TEXT;

CREATE INDEX IF NOT EXISTS idx_documents_jurisdiction ON documents(jurisdiction);
CREATE INDEX IF NOT EXISTS idx_documents_court ON documents(court);
CREATE INDEX IF NOT EXISTS idx_documents_decision_date ON documents(decision_date);
CREATE INDEX IF NOT EXISTS idx_documents_practice_area ON documents(practice_area);
