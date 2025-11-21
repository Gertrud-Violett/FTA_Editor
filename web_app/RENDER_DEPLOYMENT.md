# Deploy FTA Editor to Render.com (Free)

Quick guide to deploy the FTA Editor web application to Render.com for free.

## Prerequisites

- GitHub account
- Render.com account (free) - [Sign up here](https://render.com)
- FTA_Editor repository on GitHub

## Quick Deploy (3 Steps)

### Step 1: Push to GitHub

```bash
git add .
git commit -m "Prepare for Render deployment"
git push origin main
```

### Step 2: Connect to Render

1. Go to [dashboard.render.com](https://dashboard.render.com)
2. Click **"New +"** → **"Blueprint"**
3. Connect your GitHub repository: `FTA_Editor`
4. Render will detect `render.yaml`
5. Click **"Apply"**

### Step 3: Wait for Deployment

- Initial deployment takes 5-10 minutes
- View progress in the Render dashboard
- Your app will be live at: `https://fta-editor.onrender.com`

## Configuration Files

The repository includes all necessary files:

- ✅ `render.yaml` - Render configuration
- ✅ `requirements.txt` - Python dependencies (Flask, gunicorn)
- ✅ `web_app/app.py` - Web application
- ✅ Environment variable setup for SECRET_KEY

## Manual Setup (Alternative)

If Blueprint doesn't work, use manual setup:

1. **New Web Service**: Click "New +" → "Web Service"
2. **Connect Repository**: Select your GitHub repo
3. **Configure**:
   - Name: `fta-editor`
   - Region: Oregon (or nearest)
   - Branch: `main`
   - Runtime: **Python 3**
   - Build Command:
     ```bash
     pip install -r requirements.txt && apt-get update && apt-get install -y graphviz
     ```
   - Start Command:
     ```bash
     gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 web_app.app:app
     ```
4. **Environment Variables**:
   - `PYTHON_VERSION`: `3.11.0`
   - `SECRET_KEY`: Click "Generate"
5. **Plan**: Select **"Free"**
6. Click **"Create Web Service"**

## What You Get (Free Tier)

✅ 750 hours/month hosting  
✅ Automatic HTTPS/SSL  
✅ Auto-deploy from GitHub  
✅ Build logs and monitoring  
✅ 100 GB bandwidth/month  

⚠️ **Limitations**:
- Apps sleep after 15 minutes of inactivity
- First request after sleep takes ~30 seconds to wake up
- No custom domain (requires paid plan)

## Usage

### Access Your App

- **URL**: `https://fta-editor.onrender.com` (or your chosen name)
- **First Load**: May take 30-60 seconds (waking from sleep)
- **Subsequent Loads**: Instant (while active)

### Features Available

- ✅ Interactive fault tree editing
- ✅ Live diagram preview with zoom/pan
- ✅ Resizable panels
- ✅ Export to JSON, XML, Excel
- ✅ Import existing analyses
- ✅ AND/OR logic gate support
- ✅ Probability calculations

## Updating Your App

Render auto-deploys when you push to GitHub:

```bash
# Make changes to your code
git add .
git commit -m "Update feature"
git push origin main

# Render automatically rebuilds and deploys
# Check progress in Render dashboard
```

## Troubleshooting

### Build Fails

**Check**: Build logs in Render dashboard

**Common Issues**:
- Missing `requirements.txt` - ensure it includes Flask, gunicorn
- Graphviz not installed - verify build command includes `apt-get install -y graphviz`

**Fix**:
```bash
# Verify requirements.txt includes:
Flask>=3.0.0
Flask-Session>=0.5.0
gunicorn>=21.2.0
```

### App Won't Start

**Check**: Runtime logs in dashboard

**Common Issues**:
- Wrong start command
- PORT environment variable not set

**Fix**: Ensure start command is:
```bash
gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 web_app.app:app
```

### App is Slow/Unresponsive

**Reason**: Free tier apps sleep after 15 min inactivity

**Solutions**:
- First request wakes app (~30 seconds)
- Use a ping service to keep awake (e.g., UptimeRobot)
- Upgrade to Starter plan ($7/mo) for always-on

### Diagram Generation Fails

**Check**: Graphviz installation in build logs

**Fix**: Verify build command includes:
```bash
apt-get update && apt-get install -y graphviz
```

### Sessions Lost

**Reason**: Free tier may clear sessions during sleep

**Solution**: 
- Sessions are stored in `/tmp` which persists during active use
- Upgrade to paid plan for better persistence

## Upgrade to Paid (Optional)

For production use, consider Starter plan ($7/month):

✅ Always-on (no sleep)  
✅ Custom domains  
✅ Better performance  
✅ Persistent storage  

Upgrade in: Render Dashboard → Service Settings → Plan

## Support

- **Render Docs**: [render.com/docs](https://render.com/docs)
- **FTA Editor Issues**: [GitHub Issues](https://github.com/Gertrud-Violett/FTA_Editor/issues)
- **Full Deployment Guide**: See `DEPLOYMENT.md`

## Cost

**Free Forever** for hobby projects with limitations above.

**No credit card required** for free tier.

---

**Need Help?** Check the [full deployment guide](DEPLOYMENT.md) or open an issue on GitHub.
