-- Только выделенная учебная схема; production-таблицы не затрагиваются.
DROP SCHEMA IF EXISTS lab CASCADE;
CREATE SCHEMA lab;
SET search_path TO lab;
SELECT setseed(0.42);
CREATE TABLE orders (
 id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL,
 product_id BIGINT NOT NULL, status VARCHAR(20) NOT NULL,
 amount NUMERIC(10,2) NOT NULL, created_at TIMESTAMP NOT NULL,
 updated_at TIMESTAMP NOT NULL
);
INSERT INTO orders(user_id,product_id,status,amount,created_at,updated_at)
SELECT (random()*100000)::BIGINT,(random()*10000)::BIGINT,
 (ARRAY['NEW','PAID','DELIVERED','CANCELLED'])[floor(random()*4+1)],
 random()*10000, NOW()-random()*INTERVAL '2 years',NOW()
FROM generate_series(1,1000000);
ANALYZE orders;
CREATE TABLE users(id BIGSERIAL PRIMARY KEY,email VARCHAR(255) NOT NULL);
INSERT INTO users(email) SELECT 'user'||g||'@example.com' FROM generate_series(1,100000) g;
INSERT INTO users(email) VALUES ('Test@Example.com');
ANALYZE users;
