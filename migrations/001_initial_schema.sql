-- Initial database schema for OAuth authentication and usage tracking
-- Run with: psql $POSTGRES_URL < migrations/001_initial_schema.sql

-- Create users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    google_id VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) NOT NULL,
    name VARCHAR(255),
    picture_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for users table
CREATE INDEX IF NOT EXISTS idx_users_google_id ON users(google_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- Create usage table
CREATE TABLE IF NOT EXISTS usage (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    request_count INTEGER DEFAULT 0,
    last_request TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id)
);

-- Create index for usage table
CREATE INDEX IF NOT EXISTS idx_usage_user_id ON usage(user_id);

-- Create global usage table (single row)
CREATE TABLE IF NOT EXISTS global_usage (
    id INTEGER PRIMARY KEY DEFAULT 1,
    anonymous_count INTEGER DEFAULT 0,
    CHECK (id = 1)
);

-- Insert initial global usage record
INSERT INTO global_usage (id, anonymous_count)
VALUES (1, 0)
ON CONFLICT (id) DO NOTHING;
