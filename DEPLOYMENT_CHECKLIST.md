# Deployment Checklist

Use this checklist to deploy OAuth authentication to production.

## Pre-Deployment

### Local Development
- [ ] All dependencies installed (`pip install -r requirements.txt`)
- [ ] `.env` file configured with all required variables
- [ ] Database migration completed locally
- [ ] Local server starts without errors
- [ ] Test script passes (`python test_auth_local.py`)
- [ ] Manual testing completed (login, logout, usage tracking)
- [ ] Code committed to git

### Database Verification
- [ ] Tables created: `users`, `usage`, `global_usage`
- [ ] Indexes created on google_id, email, user_id
- [ ] Initial record in global_usage table (id=1, anonymous_count=0)
- [ ] Connection string works from local machine

### Google OAuth Setup
- [ ] Google Cloud project created
- [ ] Google+ API enabled
- [ ] OAuth consent screen configured (External, with required scopes)
- [ ] OAuth client created (Web application)
- [ ] Client ID and Secret obtained
- [ ] Local redirect URI added: `http://localhost:8000/api/auth/callback`
- [ ] Tested OAuth flow locally

## Production Setup

### Vercel Database
- [ ] Vercel Postgres database created
- [ ] Connection string (POSTGRES_URL) copied
- [ ] Migration run on production database:
  ```bash
  psql $PRODUCTION_POSTGRES_URL < migrations/001_initial_schema.sql
  ```
- [ ] Tables verified in Vercel dashboard

### Vercel Environment Variables
Add these in Vercel Dashboard → Project → Settings → Environment Variables:

- [ ] `POSTGRES_URL` (from Vercel Postgres)
  - Scope: Production, Preview, Development
- [ ] `GOOGLE_CLIENT_ID` (from Google Console)
  - Scope: Production, Preview, Development
- [ ] `GOOGLE_CLIENT_SECRET` (from Google Console)
  - Scope: Production, Preview, Development
- [ ] `JWT_SECRET_KEY` (generate with `openssl rand -hex 32`)
  - Scope: Production, Preview, Development
- [ ] `FREE_TIER_LIMIT` (default: 5)
  - Scope: Production, Preview, Development

**Security Check:**
- [ ] JWT_SECRET_KEY is random and unique (not from example)
- [ ] Google Client Secret is kept private
- [ ] Database URL uses SSL connection

### Vercel Deployment
- [ ] Code pushed to GitHub
- [ ] Vercel project connected to repository
- [ ] `vercel.json` properly configured
- [ ] Build triggered and successful
- [ ] Deployment URL obtained (e.g., `https://your-app.vercel.app`)

### Google OAuth Production
- [ ] Production redirect URI added to Google Console:
  ```
  https://your-app.vercel.app/api/auth/callback
  ```
- [ ] OAuth consent screen updated with production domain
- [ ] Test users added (if still in development mode)

## Post-Deployment Testing

### Smoke Tests
- [ ] Production site loads (`https://your-app.vercel.app`)
- [ ] Health check returns 200: `curl https://your-app.vercel.app/`
- [ ] Auth section visible in top-right corner
- [ ] Database connection working (check usage endpoint)

### Anonymous Usage Flow
- [ ] Usage counter shows "0 / 5 free requests used"
- [ ] First request succeeds
- [ ] Counter increments after each request
- [ ] 6th request shows login modal
- [ ] Modal has "Login with Google" button

### OAuth Flow
- [ ] Click "Login with Google" redirects to Google
- [ ] Google consent screen shows correct app name
- [ ] After authorization, redirects back to app
- [ ] User avatar and name appear in auth section
- [ ] User record created in database:
  ```sql
  SELECT * FROM users WHERE email = 'your-test-email@gmail.com';
  ```

### Authenticated Usage Flow
- [ ] Authenticated user can make requests beyond 5
- [ ] Usage counter shows user stats
- [ ] Each request increments user's usage counter:
  ```sql
  SELECT * FROM usage WHERE user_id = 1;
  ```
- [ ] Logout button appears
- [ ] Logout clears session and returns to logged-out state

### API Endpoints
- [ ] `GET /api/auth/me` returns 401 when not logged in
- [ ] `GET /api/auth/me` returns user info when logged in
- [ ] `GET /api/auth/usage` returns anonymous stats when not logged in
- [ ] `GET /api/auth/usage` returns user stats when logged in
- [ ] `POST /api/anonymise` works for both anonymous and authenticated
- [ ] `POST /api/anonymise` returns 401 after anonymous limit
- [ ] `POST /api/auth/logout` clears session

### Database Verification
```sql
-- Check tables exist
SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';

-- Check user records
SELECT id, email, name, created_at, last_login FROM users;

-- Check usage records
SELECT u.email, ug.request_count, ug.last_request
FROM users u
JOIN usage ug ON u.id = ug.user_id;

-- Check anonymous usage
SELECT * FROM global_usage;
```

- [ ] All queries return expected results
- [ ] Indexes present on all foreign keys
- [ ] Timestamps are being set correctly

### Security Checks
- [ ] JWT cookies are httpOnly (check in browser DevTools)
- [ ] Cookies have SameSite=lax or strict
- [ ] HTTPS enabled for production (Vercel does this automatically)
- [ ] OAuth only works with registered redirect URIs
- [ ] Environment secrets not visible in client-side code
- [ ] No sensitive data in error messages

### Browser Compatibility
- [ ] Test in Chrome
- [ ] Test in Firefox
- [ ] Test in Safari
- [ ] Test in Edge
- [ ] Test on mobile browser

### Error Handling
- [ ] Invalid JWT token returns 401
- [ ] Expired token prompts re-login
- [ ] Database connection errors are handled
- [ ] OAuth errors show user-friendly message
- [ ] Network errors don't crash the app

## Monitoring Setup

### Vercel
- [ ] Check deployment logs for errors
- [ ] Monitor function execution times
- [ ] Set up log drains if needed

### Database
- [ ] Check connection pool usage
- [ ] Monitor query performance
- [ ] Set up alerts for connection errors

### Usage Analytics
```sql
-- Daily usage query
SELECT
  DATE(last_request) as date,
  COUNT(*) as users,
  SUM(request_count) as total_requests
FROM usage
GROUP BY DATE(last_request)
ORDER BY date DESC;

-- Top users
SELECT u.email, ug.request_count
FROM users u
JOIN usage ug ON u.id = ug.user_id
ORDER BY ug.request_count DESC
LIMIT 10;

-- Anonymous usage trend
SELECT anonymous_count FROM global_usage;
```

- [ ] Queries return expected data
- [ ] Set up regular monitoring

## Documentation

- [ ] Update README with OAuth features
- [ ] Document environment variables
- [ ] Add setup instructions for new developers
- [ ] Create user guide for login flow

## Rollback Plan

If something goes wrong:

1. **Revert Deployment**
   ```bash
   vercel rollback
   ```

2. **Check Previous Version**
   - Previous code is still in git
   - Previous database state is intact
   - OAuth settings unchanged

3. **Emergency Database Rollback**
   ```sql
   -- If needed, drop new tables
   DROP TABLE IF EXISTS usage CASCADE;
   DROP TABLE IF EXISTS users CASCADE;
   DROP TABLE IF EXISTS global_usage CASCADE;
   ```

4. **Disable OAuth**
   - Remove environment variables from Vercel
   - Deploy previous version without auth code

## Success Criteria

✅ **All these should be true:**
- Anonymous users can make exactly 5 requests
- Login flow completes successfully
- Authenticated users have unlimited access
- User data persists across sessions
- No errors in Vercel logs
- Database queries are fast (< 100ms)
- Frontend loads quickly (< 2s)

## Post-Launch Tasks

### Week 1
- [ ] Monitor error rates
- [ ] Check user registration rate
- [ ] Verify usage tracking accuracy
- [ ] Collect user feedback

### Week 2
- [ ] Analyze usage patterns
- [ ] Optimize slow queries
- [ ] Add more OAuth providers (if needed)
- [ ] Plan paid tier implementation

### Month 1
- [ ] Review security logs
- [ ] Update dependencies
- [ ] Consider implementing:
  - Admin dashboard
  - Usage analytics
  - Email notifications
  - Paid tiers

## Support

If you encounter issues:

1. **Check Vercel Logs**
   ```bash
   vercel logs --follow
   ```

2. **Check Database Logs**
   - Vercel Dashboard → Storage → Your Database → Logs

3. **Check Google OAuth**
   - Google Cloud Console → APIs & Services → Credentials
   - Review OAuth consent screen settings

4. **Common Issues**
   - See `OAUTH_SETUP.md` troubleshooting section
   - Check environment variables are set
   - Verify redirect URIs match exactly

## Completion

When all items are checked:
- [ ] Take screenshots of working production app
- [ ] Document any issues encountered and solutions
- [ ] Share deployment URL with team
- [ ] Celebrate! 🎉

---

**Deployment Date:** _______________
**Deployed By:** _______________
**Production URL:** _______________
**Database:** _______________
**OAuth Provider:** Google
**Status:** ☐ In Progress  ☐ Complete  ☐ Issues Found
