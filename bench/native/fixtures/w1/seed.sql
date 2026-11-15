-- W1 fixture schema + deterministic seed. Runs once per fresh dbdata
-- volume via /docker-entrypoint-initdb.d.
CREATE TABLE IF NOT EXISTS items (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    payload TEXT NOT NULL
);

INSERT INTO items (name, payload)
SELECT 'item-' || g, md5(g::text)
FROM generate_series(1, 500) AS g
ON CONFLICT DO NOTHING;
