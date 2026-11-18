CREATE TABLE installation_metadata (
    singleton boolean PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    installation_id uuid NOT NULL DEFAULT gen_random_uuid()
);

INSERT INTO installation_metadata DEFAULT VALUES;
REVOKE ALL ON installation_metadata FROM PUBLIC;
GRANT SELECT ON installation_metadata TO civia_app;
