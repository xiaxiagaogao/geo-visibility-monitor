-- B4 L1 fields on raw_responses
ALTER TABLE raw_responses
  ADD COLUMN IF NOT EXISTS answer_status TEXT;

ALTER TABLE raw_responses
  ADD COLUMN IF NOT EXISTS annotator_version TEXT;

CREATE INDEX IF NOT EXISTS idx_raw_responses_answer_status
  ON raw_responses(answer_status);

INSERT INTO schema_migrations (id) VALUES ('002_l1_fields')
ON CONFLICT (id) DO NOTHING;
