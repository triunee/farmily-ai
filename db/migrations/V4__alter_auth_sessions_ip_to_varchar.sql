-- Hibernate 7 + PG JDBC binds String params as VARCHAR/BYTEA, neither implicitly
-- castable to PostgreSQL `inet`. The entity stores plain string IPs and the app
-- does no CIDR arithmetic, so widening the column to varchar(64) keeps the data
-- semantically identical and unblocks INSERT.

ALTER TABLE auth_sessions
    ALTER COLUMN ip TYPE varchar(64) USING ip::text;
