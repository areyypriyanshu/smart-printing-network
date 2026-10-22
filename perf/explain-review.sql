-- The two queries that matter for the phase 2 gate, with enough rows to
-- make the planner choose an index rather than a sequential scan.
--
-- Run it against the local database, from the repository root:
--
--   docker compose exec -T db psql -U spn -d spn -f - < perf/explain-review.sql
--
-- Everything happens in one transaction and is rolled back. The script
-- adds no rows to the database it is run against: the shops, the rates
-- and the orders exist only long enough to be explained. That is on
-- purpose. The point is the plan, and a real database should not be
-- left holding a load fixture.
--
-- The rows are written with SQL rather than through the services. They
-- are a measurement fixture, not product data, and the constraints
-- still apply: the price formula, the pickup code and the states are
-- checked by the database exactly as they are for a real order.

\set ON_ERROR_STOP on

BEGIN;

-- The seeded shop and customer. `make seed` creates them.
SELECT s.id AS shop_id
FROM shops s
JOIN users u ON u.id = s.owner_id
WHERE u.email = 'vendor1@example.com'
LIMIT 1
\gset

SELECT id AS customer_id
FROM users
WHERE role = 'customer'
ORDER BY created_at
LIMIT 1
\gset

\echo '== The search, with 2,000 shops around Kolkata'

INSERT INTO users (email, full_name, role)
SELECT
    'perf-explain-shop-' || g || '@example.com',
    'Perf Shop ' || g,
    'vendor'
FROM generate_series(1, 2000) AS g;

INSERT INTO shops (owner_id, name, address, location, is_verified, accepting_orders)
SELECT
    u.id,
    u.full_name,
    'Perf address ' || u.full_name,
    ST_SetSRID(
        ST_MakePoint(
            88.3639 + (random() - 0.5) * 0.2,
            22.5726 + (random() - 0.5) * 0.2
        ),
        4326
    )::geography,
    true,
    true
FROM users u
WHERE u.email LIKE 'perf-explain-shop-%@example.com';

INSERT INTO shop_rates (shop_id, paper_size, color, duplex, rate_paise)
SELECT s.id, 'A4', false, false, 200
FROM shops s
JOIN users u ON u.id = s.owner_id
WHERE u.email LIKE 'perf-explain-shop-%@example.com';

ANALYZE users;
ANALYZE shops;
ANALYZE shop_rates;

EXPLAIN (ANALYZE, BUFFERS)
SELECT
    s.id,
    ST_Y(s.location::geometry) AS lat,
    ST_X(s.location::geometry) AS lng,
    ST_Distance(
        s.location,
        ST_SetSRID(ST_MakePoint(88.3639, 22.5726), 4326)::geography
    ) AS distance_m
FROM shops s
WHERE s.is_verified
  AND s.accepting_orders
  AND ST_DWithin(
      s.location,
      ST_SetSRID(ST_MakePoint(88.3639, 22.5726), 4326)::geography,
      5000
  )
ORDER BY distance_m
LIMIT 50;

-- The price sort joins the rate and orders by the same arithmetic the
-- application writes out for the database.
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    s.id,
    r.rate_paise,
    GREATEST(
        1::bigint * 1::bigint * r.rate_paise::bigint,
        s.min_order_paise::bigint
    ) AS price_paise
FROM shops s
JOIN shop_rates r
  ON r.shop_id = s.id
 AND r.paper_size = 'A4'
 AND r.color IS FALSE
 AND r.duplex IS FALSE
WHERE s.is_verified
  AND s.accepting_orders
  AND ST_DWithin(
      s.location,
      ST_SetSRID(ST_MakePoint(88.3639, 22.5726), 4326)::geography,
      5000
  )
ORDER BY price_paise
LIMIT 50;

\echo '== The vendor queue, with 200 active orders and 20,000 finished ones'

INSERT INTO uploads (customer_id, file_key, original_filename, size_bytes, sha256, page_count)
SELECT
    :'customer_id',
    'perf-explain/' || g || '.pdf',
    'perf-explain.pdf',
    1024,
    repeat('a', 64),
    1
FROM generate_series(1, 20200) AS g;

WITH numbered AS (
    SELECT id, row_number() OVER () AS rn
    FROM uploads
    WHERE file_key LIKE 'perf-explain/%'
)
INSERT INTO orders (
    customer_id,
    shop_id,
    upload_id,
    status,
    paper_size,
    color,
    duplex,
    copies,
    page_count,
    rate_paise,
    min_order_paise,
    price_paise,
    idempotency_key,
    pickup_code,
    payment_method,
    paid_at,
    reserved_at
)
SELECT
    :'customer_id',
    :'shop_id',
    id,
    CASE WHEN rn <= 200 THEN 'RESERVED' ELSE 'COLLECTED' END,
    'A4',
    false,
    false,
    1,
    1,
    200,
    0,
    200,
    'perf-explain-' || rn,
    lpad((rn % 1000000)::text, 6, '0'),
    'at_store',
    CASE WHEN rn > 200 THEN now() ELSE NULL END,
    now() - (rn || ' seconds')::interval
FROM numbered;

ANALYZE orders;
ANALYZE uploads;

EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM orders
WHERE shop_id = :'shop_id'
  AND status IN ('PAID', 'RESERVED', 'ACCEPTED', 'PRINTING', 'READY')
ORDER BY reserved_at ASC, order_no ASC
LIMIT 100;

ROLLBACK;
