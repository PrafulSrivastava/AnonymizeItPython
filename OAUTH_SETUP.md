# OAuth Authentication & Usage Tracking Setup Guide

This guide will walk you through setting up OAuth authentication with Google and usage tracking for the WhatsApp Anonymization API.

## Overview

The system implements:
- ✅ Google OAuth 2.0 authentication
- ✅ JWT-based session management
- ✅ Anonymous usage limits (5 free requests)
- ✅ Unlimited access for authenticated users
- ✅ PostgreSQL database for user and usage tracking

## Architecture

```
Anonymous User → API Request → Check Global Counter
├─ If < 5: Process & Increment
└─ If ≥ 5: Return 401 → Show Login Modal

Authenticated User → API Request → Verify JWT → Process & Track
```

## Prerequisites

- Vercel account
- Google Cloud Platform account
- PostgreSQL database (Vercel Postgres recommended)

## Step 1: Database Setup

### 1.1 Create Vercel Postgres Database

1. Go to your Vercel dashboard
2. Navigate to **Storage** → **Create Database** → **Postgres**
3. Choose a region close to your deployment
4. Wait for provisioning to complete
5. Copy the `POSTGRES_URL` connection string

### 1.2 Run Database Migration

```bash
# Connect to your database and run the migration
psql $POSTGRES_URL < migrations/001_initial_schema.sql
```

Or using the Vercel Postgres UI:
1. Go to Storage → Your Database → Query
2. Copy and paste the contents of `migrations/001_initial_schema.sql`
3. Click "Run Query"

### 1.3 Verify Tables

```sql
-- Check that tables were created
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public';

-- Should show: users, usage, global_usage
```

## Step 2: Google OAuth Setup

### 2.1 Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project: **"WhatsApp Anonymizer"**
3. Enable **Google+ API** (or Google Identity Platform)

### 2.2 Configure OAuth Consent Screen

1. Navigate to **APIs & Services** → **OAuth consent screen**
2. Select **External** user type
3. Fill in application details:
   - **App name**: WhatsApp Anonymization Platform
   - **User support email**: Your email
   - **Developer contact**: Your email
4. Add scopes:
   - `email`
   - `profile`
   - `openid`
5. Add test users (for development)
6. Click **Save and Continue**

### 2.3 Create OAuth Credentials

1. Go to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **OAuth 2.0 Client ID**
3. Select **Web application**
4. Configure:
   - **Name**: WhatsApp Anonymizer Web Client
   - **Authorized JavaScript origins**:
     ```
     http://localhost:8000
     https://your-app.vercel.app
     ```
   - **Authorized redirect URIs**:
     ```
     http://localhost:8000/api/auth/callback
     https://your-app.vercel.app/api/auth/callback
     ```
5. Click **Create**
6. **Copy the Client ID and Client Secret** (you'll need these next)

## Step 3: Environment Variables

### 3.1 Local Development

Create a `.env` file (use `.env.example` as template):

```bash
# Database
POSTGRES_URL=postgresql://user:password@host:5432/database

# Google OAuth
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret

# JWT Secret (generate with: openssl rand -hex 32)
JWT_SECRET_KEY=your-random-secret-key-here

# Usage Limits
FREE_TIER_LIMIT=5
```

### 3.2 Vercel Production

Add environment variables in Vercel dashboard or via CLI:

```bash
# Using Vercel CLI
vercel env add POSTGRES_URL production
vercel env add GOOGLE_CLIENT_ID production
vercel env add GOOGLE_CLIENT_SECRET production
vercel env add JWT_SECRET_KEY production
vercel env add FREE_TIER_LIMIT production
```

Or in **Vercel Dashboard**:
1. Go to your project → Settings → Environment Variables
2. Add each variable for **Production**, **Preview**, and **Development**

## Step 4: Local Testing

### 4.1 Install Dependencies

```bash
pip install -r requirements.txt
```

### 4.2 Run Local Server

```bash
uvicorn api.anonymise:app --reload --port 8000
```

### 4.3 Test Anonymous Usage

```bash
# Test first request (should work)
curl -X POST http://localhost:8000/api/anonymise \
  -H "Content-Type: application/json" \
  -d '{
    "rawText": "[26/02/2026, 09:14] Test: Hello",
    "blocklist": "",
    "sessionId": "test1"
  }'

# Make 5 requests total...

# Test 6th request (should return 401)
curl -X POST http://localhost:8000/api/anonymise \
  -H "Content-Type: application/json" \
  -d '{
    "rawText": "[26/02/2026, 09:14] Test: Hello",
    "blocklist": "",
    "sessionId": "test6"
  }'
```

### 4.4 Test OAuth Flow

1. Open browser to http://localhost:8000
2. Try making a request - should see usage counter
3. Make 5 requests until limit is reached
4. Should see "Login Required" modal
5. Click "Login with Google"
6. Complete OAuth flow
7. Should redirect back with authentication
8. Make additional requests - should work without limit

### 4.5 Test Authentication Endpoints

```bash
# Check current user (should return 401 if not logged in)
curl http://localhost:8000/api/auth/me \
  -H "Cookie: access_token=YOUR_TOKEN"

# Check usage stats
curl http://localhost:8000/api/auth/usage

# Logout
curl -X POST http://localhost:8000/api/auth/logout \
  -H "Cookie: access_token=YOUR_TOKEN"
```

## Step 5: Deploy to Vercel

### 5.1 Update vercel.json

The `vercel.json` is already configured, but verify:

```json
{
  "functions": {
    "api/anonymise.py": {
      "runtime": "python3.11",
      "maxDuration": 30
    }
  },
  "routes": [
    {
      "src": "/api/(.*)",
      "dest": "/api/anonymise.py"
    },
    {
      "src": "/",
      "dest": "/public/index.html"
    }
  ],
  "env": {
    "FREE_TIER_LIMIT": "5"
  }
}
```

### 5.2 Deploy

```bash
# Deploy to Vercel
vercel --prod

# Or via GitHub integration (push to main branch)
git push origin main
```

### 5.3 Update Google OAuth Redirect URIs

After deployment, add your Vercel production URL to Google OAuth:
1. Go to Google Cloud Console → Credentials
2. Edit your OAuth client
3. Add to **Authorized redirect URIs**:
   ```
   https://your-actual-domain.vercel.app/api/auth/callback
   ```

## Step 6: Verify Production Deployment

### 6.1 Check Database Connection

```bash
# SSH into Vercel function (or use logs)
vercel logs

# Should see successful database connections
```

### 6.2 Test Production Flow

1. Visit your production URL
2. Test anonymous usage (5 requests)
3. Test login flow
4. Verify authenticated requests work
5. Check database for user records:

```sql
SELECT * FROM users;
SELECT * FROM usage;
SELECT * FROM global_usage;
```

## Step 7: Monitor and Maintain

### 7.1 Check Usage Stats

```sql
-- Total users
SELECT COUNT(*) FROM users;

-- Total anonymous requests
SELECT anonymous_count FROM global_usage;

-- Top users by request count
SELECT u.email, ug.request_count
FROM users u
JOIN usage ug ON u.id = ug.user_id
ORDER BY ug.request_count DESC
LIMIT 10;
```

### 7.2 Reset Anonymous Counter (Optional)

If you want to reset the anonymous counter periodically:

```sql
UPDATE global_usage SET anonymous_count = 0 WHERE id = 1;
```

Or via Python:

```python
from lib.usage.tracker import reset_anonymous_usage
reset_anonymous_usage()
```

## Troubleshooting

### OAuth Errors

**Error: redirect_uri_mismatch**
- Verify redirect URI in Google Console exactly matches your deployment URL
- Include `/api/auth/callback` path
- Check for http vs https

**Error: access_denied**
- User cancelled OAuth flow
- Check OAuth consent screen is configured for external users
- Verify required scopes are enabled

### Database Errors

**Error: relation "users" does not exist**
- Run migration: `psql $POSTGRES_URL < migrations/001_initial_schema.sql`

**Error: connection refused**
- Verify `POSTGRES_URL` environment variable is set
- Check database is accessible from Vercel

### JWT Errors

**Error: Invalid or expired token**
- Token expired (30 days default)
- User needs to login again
- Check `JWT_SECRET_KEY` matches across deployments

**Error: Not authenticated**
- Cookie not being sent (check SameSite settings)
- User hasn't logged in
- Cookie expired or cleared

### Usage Tracking Errors

**Anonymous limit not working**
- Check `global_usage` table has record with id=1
- Verify `FREE_TIER_LIMIT` environment variable is set

**Usage not incrementing**
- Check database connection
- Verify middleware is running
- Check for transaction errors in logs

## Security Considerations

1. **JWT Secret**: Use a strong random secret (32+ characters)
2. **HTTPS Only**: Enable secure cookies in production
3. **CORS**: Configure allowed origins appropriately
4. **Rate Limiting**: Consider adding per-IP rate limits
5. **Database**: Use connection pooling, enable SSL
6. **Secrets**: Never commit `.env` to git

## Future Enhancements

- [ ] Add more OAuth providers (GitHub, Microsoft)
- [ ] Implement paid tiers with Stripe
- [ ] Add admin dashboard for user management
- [ ] Email notifications for quota warnings
- [ ] API keys for programmatic access
- [ ] Usage analytics and reporting
- [ ] Password reset for email/password auth

## Support

For issues or questions:
- Check Vercel logs: `vercel logs`
- Check database logs in Vercel dashboard
- Review Google Cloud Console for OAuth errors
- Open an issue on GitHub

## References

- [Google OAuth Documentation](https://developers.google.com/identity/protocols/oauth2)
- [Vercel Postgres Documentation](https://vercel.com/docs/storage/vercel-postgres)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
- [Authlib Documentation](https://docs.authlib.org/)
