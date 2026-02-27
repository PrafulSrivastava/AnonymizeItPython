# OAuth Authentication - Quick Start Guide

Get up and running with OAuth authentication in 15 minutes.

## Prerequisites

- Python 3.11+
- PostgreSQL database (or Vercel Postgres)
- Google Cloud account

## Step 1: Install Dependencies (2 min)

```bash
pip install -r requirements.txt
```

New dependencies added:
- `sqlalchemy` - Database ORM
- `psycopg2-binary` - PostgreSQL adapter
- `python-jose` - JWT tokens
- `authlib` - OAuth client
- `itsdangerous` - Security utilities
- `python-multipart` - Form data parsing

## Step 2: Set Up Database (3 min)

### Option A: Vercel Postgres (Recommended)

1. Go to [Vercel Dashboard](https://vercel.com/dashboard)
2. Storage → Create Database → Postgres
3. Copy the connection string
4. Run migration:

```bash
# Set connection string
export POSTGRES_URL="postgresql://..."

# Run migration
psql $POSTGRES_URL < migrations/001_initial_schema.sql
```

### Option B: Local PostgreSQL

```bash
# Create database
createdb whatsapp_anonymizer

# Run migration
psql whatsapp_anonymizer < migrations/001_initial_schema.sql
```

## Step 3: Set Up Google OAuth (5 min)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create project: "WhatsApp Anonymizer"
3. Enable Google+ API
4. OAuth consent screen:
   - App name: "WhatsApp Anonymization Platform"
   - Scopes: email, profile, openid
5. Create OAuth Client:
   - Type: Web application
   - Redirect URI: `http://localhost:8000/api/auth/callback`
6. Copy Client ID and Secret

## Step 4: Configure Environment (2 min)

Create `.env` file:

```bash
cp .env.example .env
```

Edit `.env`:

```env
POSTGRES_URL=postgresql://user:password@host:5432/database
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
JWT_SECRET_KEY=$(openssl rand -hex 32)
FREE_TIER_LIMIT=5
```

**Generate JWT secret:**
```bash
openssl rand -hex 32
```

## Step 5: Test Locally (3 min)

### Start Server

```bash
uvicorn api.anonymise:app --reload --port 8000
```

### Run Test Suite

In another terminal:

```bash
python test_auth_local.py
```

### Manual Testing

1. Open http://localhost:8000
2. Try making 5 requests (watch the counter)
3. 6th request should show "Login Required" modal
4. Click "Login with Google"
5. Complete OAuth flow
6. Verify avatar appears
7. Make more requests (should work)

## Step 6: Deploy to Vercel (Optional)

### Add Environment Variables

```bash
vercel env add POSTGRES_URL production
vercel env add GOOGLE_CLIENT_ID production
vercel env add GOOGLE_CLIENT_SECRET production
vercel env add JWT_SECRET_KEY production
vercel env add FREE_TIER_LIMIT production
```

### Update Google OAuth

Add production redirect URI:
```
https://your-app.vercel.app/api/auth/callback
```

### Deploy

```bash
vercel --prod
```

## Verification Checklist

- [ ] Database migration completed (3 tables created)
- [ ] Environment variables set
- [ ] Local server starts without errors
- [ ] Anonymous usage counter works (0-5 requests)
- [ ] Login redirects to Google
- [ ] OAuth callback creates user in database
- [ ] Authenticated users can make unlimited requests
- [ ] Logout clears session
- [ ] Frontend shows usage counter
- [ ] Frontend shows user avatar when logged in

## Quick Commands Reference

```bash
# Start local server
uvicorn api.anonymise:app --reload --port 8000

# Test anonymous usage (should fail on 6th)
for i in {1..6}; do
  curl -X POST http://localhost:8000/api/anonymise \
    -H "Content-Type: application/json" \
    -d '{"rawText":"[26/02/2026, 09:14] Test: Hello","blocklist":"","sessionId":"test"}'
done

# Check usage stats
curl http://localhost:8000/api/auth/usage

# Check database
psql $POSTGRES_URL -c "SELECT * FROM users;"
psql $POSTGRES_URL -c "SELECT * FROM usage;"
psql $POSTGRES_URL -c "SELECT * FROM global_usage;"

# Reset anonymous counter (for testing)
psql $POSTGRES_URL -c "UPDATE global_usage SET anonymous_count = 0;"

# Deploy to Vercel
vercel --prod
```

## Troubleshooting

### "Cannot connect to server"
- Make sure server is running: `uvicorn api.anonymise:app --reload`

### "Database connection failed"
- Check `POSTGRES_URL` is set correctly
- Verify database is accessible
- Run migration if tables don't exist

### "OAuth redirect_uri_mismatch"
- Verify redirect URI in Google Console matches exactly
- Include `/api/auth/callback` path
- Check http vs https

### "Invalid JWT token"
- Token expired (30 days)
- Different `JWT_SECRET_KEY` between restarts
- Clear cookies and login again

## File Structure

```
New/Modified Files:
├── api/anonymise.py              # Auth endpoints added
├── lib/
│   ├── auth/                     # NEW: Auth module
│   │   ├── jwt.py
│   │   ├── oauth.py
│   │   └── middleware.py
│   ├── db/                       # NEW: Database module
│   │   ├── connection.py
│   │   └── models.py
│   └── usage/                    # NEW: Usage tracking
│       └── tracker.py
├── migrations/
│   └── 001_initial_schema.sql    # NEW: Database schema
├── public/index.html             # Auth UI added
├── requirements.txt              # Dependencies added
├── vercel.json                   # Routes updated
├── .env.example                  # NEW: Env template
├── OAUTH_SETUP.md                # NEW: Full setup guide
├── QUICKSTART.md                 # NEW: This file
└── test_auth_local.py            # NEW: Test script
```

## What You Get

✅ **For Anonymous Users:**
- 5 free requests
- Usage counter displayed
- Login prompt when limit reached

✅ **For Authenticated Users:**
- Unlimited requests
- Usage tracking per user
- Persistent login (30 days)

✅ **For You:**
- User database with OAuth profiles
- Usage analytics
- Ready for monetization
- Expandable to more OAuth providers

## Next Steps

1. **Test thoroughly** - Use `test_auth_local.py`
2. **Deploy to production** - Follow deployment steps above
3. **Add more providers** - GitHub, Microsoft, etc.
4. **Implement paid tiers** - Add Stripe integration
5. **Build admin dashboard** - User management

## Need Help?

- **Full setup guide**: See `OAUTH_SETUP.md`
- **Implementation details**: See `IMPLEMENTATION_SUMMARY.md`
- **Issues**: Check Vercel logs or database errors

## Architecture Summary

```
┌─────────────────┐
│  Anonymous User │──────► Global Counter (0-5)
└─────────────────┘              │
                                 ├─ < 5: Process ✓
                                 └─ ≥ 5: Login Required ✗

┌─────────────────┐
│ Authenticated   │──────► JWT Cookie ──► User Counter (unlimited)
│ User (Google)   │
└─────────────────┘
```

**Database:**
- `users` - OAuth profiles
- `usage` - Per-user request counts
- `global_usage` - Anonymous counter

**Frontend:**
- Auth section (top-right)
- Login modal on limit
- Usage counter display

**Backend:**
- 5 auth endpoints
- JWT session management
- Usage tracking middleware

Total: **~2,000 lines** across 15+ files. Production-ready! 🚀
