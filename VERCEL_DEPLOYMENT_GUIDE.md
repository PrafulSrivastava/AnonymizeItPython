# Vercel Deployment Guide - Updated for 2026

## ✅ Configuration Verified Against Official Docs

This guide is based on the official Vercel documentation (as of Feb 2026):
- [Project Configuration](https://vercel.com/docs/project-configuration)
- [vercel.json Reference](https://vercel.com/docs/projects/project-configuration/vercel-json)
- [Python Runtime](https://vercel.com/docs/functions/runtimes/python)

## What Changed in vercel.json

### ❌ Old Configuration (DEPRECATED)
```json
{
  "version": 2,
  "builds": [
    {
      "src": "api/anonymise.py",
      "use": "@vercel/python"
    }
  ],
  "routes": [
    {
      "src": "/api/(.*)",
      "dest": "/api/anonymise.py"
    }
  ]
}
```

**Problems:**
- ❌ `version` - Legacy property, not needed
- ❌ `builds` - Deprecated, Vercel auto-detects Python files
- ❌ `routes` - Replaced by `rewrites` and `redirects`

### ✅ New Configuration (CURRENT)
```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "functions": {
    "api/**/*.py": {
      "memory": 1024,
      "maxDuration": 30,
      "excludeFiles": "{tests/**,__tests__/**,**/*.test.py}"
    }
  },
  "rewrites": [
    {
      "source": "/api/:path*",
      "destination": "/api/:path*"
    }
  ],
  "headers": [...]
}
```

**Benefits:**
- ✅ `$schema` - Enables IDE autocomplete and validation
- ✅ `functions` - Modern way to configure Python serverless functions
- ✅ `rewrites` - Current routing method
- ✅ `headers` - CORS configuration for OAuth
- ✅ `excludeFiles` - Keeps bundle size under 500MB limit

## How Vercel Auto-Detection Works

### For Python Projects:
1. **Automatic detection**: Vercel scans your project for `api/*.py` files
2. **No builds needed**: Python runtime is automatically applied
3. **Zero config option**: For simple projects, you can deploy without `vercel.json`

### File Structure:
```
your-project/
├── api/
│   ├── anonymise.py      # Auto-detected as serverless function
│   └── __init__.py       # Optional
├── public/
│   └── index.html        # Auto-served as static file
├── lib/                  # Your Python modules
├── requirements.txt      # Dependencies auto-installed
└── vercel.json          # Optional configuration
```

## Deployment Steps

### 1. Environment Variables (REQUIRED)

Set these in **Vercel Dashboard → Project Settings → Environment Variables**:

| Variable | Value | Where to Get |
|----------|-------|--------------|
| `POSTGRES_URL` | `postgresql://...` | Vercel Storage → Postgres |
| `GOOGLE_CLIENT_ID` | `xxx.apps.googleusercontent.com` | Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | `GOCSPX-...` | Google Cloud Console |
| `JWT_SECRET_KEY` | Random 32-char string | `openssl rand -hex 32` |
| `FREE_TIER_LIMIT` | `5` | Your preference |

**Important**: Set for **Production**, **Preview**, and **Development** environments.

### 2. Google OAuth Setup

Update your OAuth redirect URIs to include production URL:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. APIs & Services → Credentials → Your OAuth Client
3. Add to **Authorized redirect URIs**:
   ```
   https://your-app.vercel.app/api/auth/callback
   ```

### 3. Deploy Options

#### Option A: GitHub Integration (Recommended)

1. **Connect Repository**:
   - Vercel Dashboard → Add New → Project
   - Import from GitHub
   - Select your repository

2. **Configure Build**:
   - Framework Preset: **Other**
   - Build Command: (leave empty - auto-detected)
   - Output Directory: (leave empty - auto-detected)
   - Install Command: `pip install -r requirements.txt` (auto-detected)

3. **Deploy**:
   - Click "Deploy"
   - Vercel automatically builds and deploys
   - Get deployment URL

#### Option B: Vercel CLI

```bash
# Install Vercel CLI
npm install -g vercel

# Login
vercel login

# Deploy to production
vercel --prod
```

### 4. Verify Deployment

After deployment, test these endpoints:

```bash
# Health check
curl https://your-app.vercel.app/

# Usage stats
curl https://your-app.vercel.app/api/auth/usage

# Try to login (should redirect to Google)
curl -I https://your-app.vercel.app/api/auth/login
```

## Configuration Reference

### functions

Configure Python serverless functions:

```json
{
  "functions": {
    "api/**/*.py": {
      "memory": 1024,        // Memory in MB (128-3008)
      "maxDuration": 30,     // Timeout in seconds (1-900)
      "excludeFiles": "..."  // Files to exclude from bundle
    }
  }
}
```

**Memory limits:**
- Hobby: 1024 MB max
- Pro: 3008 MB max

**Duration limits:**
- Hobby: 10 seconds max
- Pro: 60 seconds max (can request up to 900s)

### rewrites

Route requests without changing the URL:

```json
{
  "rewrites": [
    {
      "source": "/api/:path*",
      "destination": "/api/:path*"
    }
  ]
}
```

### headers

Add custom HTTP headers (useful for CORS):

```json
{
  "headers": [
    {
      "source": "/api/(.*)",
      "headers": [
        { "key": "Access-Control-Allow-Credentials", "value": "true" }
      ]
    }
  ]
}
```

## Bundle Size Optimization

Python functions have a **500 MB uncompressed bundle size limit**.

### Reduce Bundle Size:

1. **Exclude test files**:
   ```json
   {
     "functions": {
       "api/**/*.py": {
         "excludeFiles": "{tests/**,__tests__/**,**/*.test.py,**/test_*.py}"
       }
     }
   }
   ```

2. **Minimize dependencies**:
   - Only include runtime dependencies in `requirements.txt`
   - Remove dev dependencies
   - Use lighter alternatives when possible

3. **Check bundle size**:
   - View in Vercel Dashboard → Deployment → Resources tab
   - Each function shows its size

## Common Issues & Solutions

### Issue: "Function Runtimes must have a valid version"
**Solution**: Remove `builds` and `version` from `vercel.json` - they're deprecated.

### Issue: CORS errors
**Solution**: Ensure `headers` are configured in `vercel.json` with CORS headers.

### Issue: OAuth redirect_uri_mismatch
**Solution**: Add production URL to Google OAuth authorized redirect URIs.

### Issue: SessionMiddleware error
**Solution**: Ensure `SessionMiddleware` is added in `api/anonymise.py` (already done).

### Issue: Database connection failed
**Solution**: Verify `POSTGRES_URL` environment variable is set in Vercel.

### Issue: Module not found errors
**Solution**: Ensure all dependencies are in `requirements.txt`.

## Best Practices

1. **✅ Use $schema**: Enables autocomplete in IDE
2. **✅ Set memory appropriately**: 1024 MB is good for most Python apps
3. **✅ Exclude unnecessary files**: Keeps bundles small
4. **✅ Use environment variables**: Never hardcode secrets
5. **✅ Test locally first**: Use `vercel dev` for local testing
6. **✅ Monitor bundle size**: Check in deployment details

## Local Development

Test your Vercel configuration locally:

```bash
# Install dependencies
pip install -r requirements.txt

# Run Vercel dev server
vercel dev

# Access at http://localhost:3000
```

This simulates the Vercel environment locally, including:
- Serverless function execution
- Environment variables from Vercel
- Routing configuration

## Production Checklist

Before deploying to production:

- [ ] All environment variables set in Vercel
- [ ] Google OAuth redirect URIs updated with production URL
- [ ] Database migration run on production database
- [ ] `vercel.json` uses modern configuration (no `builds`/`routes`)
- [ ] Bundle size under 500 MB
- [ ] Test files excluded from bundle
- [ ] CORS headers configured
- [ ] Local testing completed with `vercel dev`

## Monitoring

After deployment:

1. **Check deployment logs**: Dashboard → Deployments → View Logs
2. **Monitor function execution**: Dashboard → Analytics
3. **Check errors**: Dashboard → Logs
4. **View resources**: Dashboard → Resources tab

## Additional Resources

- [Vercel Python Runtime Docs](https://vercel.com/docs/functions/runtimes/python)
- [FastAPI on Vercel Guide](https://vercel.com/docs/frameworks/backend/fastapi)
- [Project Configuration Reference](https://vercel.com/docs/project-configuration/vercel-json)
- [Deployment Documentation](https://vercel.com/docs/deployments)

## Summary

✅ **Modern Configuration**:
- No `builds` or `routes` (deprecated)
- Use `functions`, `rewrites`, `headers` instead
- Auto-detection handles most cases
- `vercel.json` is optional for simple projects

✅ **Ready to Deploy**:
- Configuration verified against official docs
- Follows Vercel best practices
- Optimized for Python serverless functions
- CORS and OAuth properly configured

Your project is now configured correctly and ready to deploy! 🚀
