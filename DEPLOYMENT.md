# FTA/ETA Editor Deployment Guide

Version: 1.4.2  
Last Updated: November 25, 2025

## Overview

This guide covers deployment options for the FTA/ETA Editor application, including local installation, Docker deployment, and production considerations.

## Prerequisites

### System Requirements

- **Operating System**: Windows, Linux, or macOS
- **Python**: 3.14 or higher
- **Graphviz**: Required for diagram generation
- **Memory**: 512 MB RAM minimum, 1 GB recommended
- **Disk Space**: 100 MB minimum

### Software Dependencies

1. **Python 3.14+**
   - Download from [python.org](https://www.python.org/downloads/)
   - Ensure pip is installed

2. **Graphviz**
   - Linux: `sudo apt-get install graphviz`
   - macOS: `brew install graphviz`
   - Windows: Download from [graphviz.org](https://graphviz.org/download/) and add to PATH

3. **Python Packages**
   - See `requirements.txt` for full list
   - Main dependencies: openpyxl, Pillow

## Deployment Options

### Option 1: Render.com (Web Application - Free Hosting)

**Best for**: Production web application, public access, zero-cost hosting

#### Overview
Render.com provides free hosting for web applications with automatic deployments from GitHub. The FTA Editor web application can be deployed with just a few clicks.

#### Prerequisites
- GitHub account with FTA_Editor repository
- Render.com account (free tier available)
- Repository pushed to GitHub

#### Deployment Steps

**Step 1: Prepare Repository**

The repository already includes `render.yaml` for automatic configuration. Ensure these files are present:
- `render.yaml` - Render configuration
- `requirements.txt` - Python dependencies (includes Flask, gunicorn)
- `web_app/app.py` - Web application entry point

**Step 2: Create Render Account**

1. Go to [render.com](https://render.com)
2. Sign up with GitHub account
3. Authorize Render to access your repositories

**Step 3: Deploy Application**

**Method A: Automatic (Using Blueprint)**
1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click "New +" → "Blueprint"
3. Connect your GitHub repository: `Gertrud-Violett/FTA_Editor`
4. Render will detect `render.yaml` and configure automatically
5. Click "Apply" to deploy

**Method B: Manual Setup**
1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click "New +" → "Web Service"
3. Connect your GitHub repository
4. Configure:
   - **Name**: `fta-editor`
   - **Region**: Oregon (US West) or closest to your location
   - **Branch**: `main`
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 web_app.app:app`
5. Add Environment Variables:
   - `PYTHON_VERSION`: `3.14.0`
   - `SECRET_KEY`: (Click "Generate" for secure random key)
6. Select "Free" plan
7. Click "Create Web Service"

**Step 4: Install System Dependencies**

Render automatically installs Graphviz via the build command in `render.yaml`. If using manual setup, add to Build Command:
```bash
pip install -r requirements.txt && apt-get update && apt-get install -y graphviz
```

**Step 5: Access Application**

Once deployed (takes 5-10 minutes first time):
- Your app will be at: `https://fta-editor.onrender.com` (or your custom name)
- First access may take 30-60 seconds (free tier apps sleep after 15 min inactivity)

#### Configuration Options

**Environment Variables** (optional):
- `SECRET_KEY`: Flask secret key (auto-generated recommended)
- `PORT`: Automatically set by Render (default: 5000)
- `PYTHON_VERSION`: Python version to use (default: 3.14.0)

**Custom Domain** (optional, requires paid plan):
1. Go to Service Settings → Custom Domains
2. Add your domain and configure DNS

**Auto-Deploy**:
- Enabled by default
- Every push to `main` branch triggers new deployment
- View build logs in Render dashboard

#### Free Tier Limitations

- **Sleep after inactivity**: App sleeps after 15 minutes with no requests
  - First request after sleep takes ~30 seconds to wake up
  - Subsequent requests are instant
- **750 hours/month**: Free for hobby use
- **No custom domain**: Requires paid plan
- **Shared resources**: May be slower during peak times

#### Production Considerations

**For Production Use** (Paid Plans):
- Upgrade to Starter plan ($7/month) for:
  - No sleep/always-on
  - Custom domains
  - Better performance
  - More build minutes

**Monitoring**:
- View logs in Render Dashboard → Logs tab
- Set up health checks (automatically configured in `render.yaml`)

**Scaling**:
- Increase workers in start command for more traffic
- Upgrade plan for better resources

#### Troubleshooting

**Build Fails:**
- Check build logs in Render dashboard
- Verify `requirements.txt` is correct
- Ensure Graphviz installation is in build command

**App Won't Start:**
- Check runtime logs
- Verify start command: `gunicorn web_app.app:app`
- Ensure Flask app variable is named `app`

**Diagram Generation Fails:**
- Verify Graphviz is installed during build
- Check `apt-get install -y graphviz` is in build command

**Session Issues:**
- Free tier may lose sessions during sleep
- Upgrade to paid plan for persistent sessions

#### Updating the Application

**Automatic Updates:**
```bash
git add .
git commit -m "Update application"
git push origin main
# Render automatically deploys
```

**Manual Redeploy:**
1. Go to Render Dashboard
2. Select your service
3. Click "Manual Deploy" → "Deploy latest commit"

**Rollback:**
1. Go to Render Dashboard → Events
2. Find previous successful deploy
3. Click "Rollback to this version"

#### Cost Comparison

| Feature | Free Tier | Starter ($7/mo) |
|---------|-----------|-----------------|
| Always-on | No (sleeps) | Yes |
| Build minutes | 500/mo | 500/mo |
| Bandwidth | 100 GB/mo | 100 GB/mo |
| Custom domains | No | Yes |
| SSL | Yes | Yes |

### Option 2: Local Python Installation

**Best for**: Development, single-user installations, testing

#### Installation Steps

```bash
# Clone repository
git clone https://github.com/Gertrud-Violett/FTA_Editor.git
cd FTA_Editor

# Install Python dependencies
pip install -r requirements.txt

# Install Graphviz (system package)
# Linux:   sudo apt-get install graphviz
# macOS:   brew install graphviz
# Windows: Download and install from graphviz.org

# Run application
python src/FTA_Editor_UI.py
```

#### Advantages
- Direct access to source code
- Easy debugging and modification
- No containerization overhead

#### Considerations
- Requires Python environment setup
- System-specific dependencies
- Manual dependency management

### Option 3: Docker Deployment

**Best for**: Production, multi-user environments, isolated deployments

#### Quick Start

```bash
# Clone repository
git clone https://github.com/Gertrud-Violett/FTA_Editor.git
cd FTA_Editor

# Build and run with Docker Compose
docker-compose up

# Or run in detached mode
docker-compose up -d
```

#### Detailed Docker Setup

**Build Image:**
```bash
docker build -t fta-editor:2.2.1 .
```

**Run Container:**
```bash
docker run -it --rm \
  -e DISPLAY=$DISPLAY \
  -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/output:/app/output \
  fta-editor:2.2.1
```

**Using Docker Compose:**
```bash
# Start
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down

# Rebuild after changes
docker-compose up --build
```

#### X11 Display Configuration

**Linux:**
```bash
xhost +local:docker
docker-compose up
```

**macOS:**
```bash
# Install XQuartz
brew install --cask xquartz

# Start XQuartz, enable network clients in Preferences → Security
IP=$(ifconfig en0 | grep inet | awk '$1=="inet" {print $2}')
xhost + $IP
DISPLAY=$IP:0 docker-compose up
```

**Windows:**
```powershell
# Install VcXsrv or Xming
# Start X server with access control disabled
$env:DISPLAY="host.docker.internal:0"
docker-compose up
```

#### Advantages
- Consistent environment across platforms
- Isolated dependencies
- Easy updates and rollbacks
- Simplified deployment

#### Considerations
- Requires Docker installation
- X11 configuration for GUI
- Slightly larger disk footprint

### Option 4: Docker Hub Distribution

**Best for**: Quick deployment without building

```bash
# Pull image (when available)
docker pull username/fta-editor:2.2.1

# Run
docker run -it --rm username/fta-editor:2.2.1
```

## Production Deployment

### Security Considerations

1. **User Permissions**
   - Container runs as non-root user (uid 1000)
   - Limited file system access via volumes

2. **Network Isolation**
   - Uses host network for X11 display
   - No exposed ports for network services

3. **Data Volumes**
   - Mount only necessary directories
   - Use read-only mounts where appropriate

### Volume Management

**Data Directory** (Read/Write):
```yaml
volumes:
  - ./data:/app/data
```

**Output Directory** (Read/Write):
```yaml
volumes:
  - ./output:/app/output
```

**Application Directory** (Read-Only - recommended for production):
```yaml
volumes:
  - ./src:/app/src:ro
```

### Environment Variables

Configure via docker-compose.yml:

```yaml
environment:
  - DISPLAY=${DISPLAY:-:0}
  - PYTHONUNBUFFERED=1
  - LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR
```

### Backup and Recovery

**Backup Important Directories:**
```bash
# Backup data and output
tar -czf fta_backup_$(date +%Y%m%d).tar.gz data/ output/

# Restore
tar -xzf fta_backup_20251101.tar.gz
```

**Version Control:**
- Keep analysis files in version control (Git)
- Tag important versions
- Document changes in commit messages

### Monitoring

**View Container Logs:**
```bash
docker-compose logs -f fta-editor
```

**Check Container Status:**
```bash
docker-compose ps
docker stats fta_editor_app
```

**Resource Usage:**
```bash
docker system df
docker system prune -a  # Clean up unused resources
```

## Updating the Application

### Docker Update Process

```bash
# Pull latest changes
git pull origin main

# Rebuild and restart
docker-compose down
docker-compose up --build -d

# Or force rebuild
docker-compose build --no-cache
docker-compose up -d
```

### Local Installation Update

```bash
# Pull latest changes
git pull origin main

# Update dependencies
pip install -r requirements.txt --upgrade

# Restart application
python src/FTA_Editor_UI.py
```

## Troubleshooting

### Common Issues

**1. Graphviz Not Found**
```
Error: Graphviz 'dot' not found
Solution: Install Graphviz and ensure it's in PATH
```

**2. X11 Display Error**
```
Error: cannot open display
Solution: Configure X11 forwarding (see X11 Display Configuration above)
```

**3. Permission Denied on Volumes**
```
Error: Permission denied on /app/data
Solution: Check volume mount permissions, ensure uid 1000 has access
```

**4. AND Gate Calculation Issues**
```
Issue: Probabilities seem incorrect for AND gates
Solution: Upgrade to v2.2.1 which fixes AND gate calculation
```

### Debug Mode

**Enable verbose logging:**
```bash
# Docker
docker-compose run --rm fta-editor python -u src/FTA_Editor_UI.py

# Local
python -u src/FTA_Editor_UI.py
```

## Version History

### v2.2.1 (2025-11-01)
- **CRITICAL FIX**: AND gate probability calculation
- **IMPROVED**: Logic gates displayed in node boxes
- **ENHANCED**: Cleaner diagram visualization

### v2.2.0 (2025-10-31)
- Added ETA mode support
- Hierarchical Excel export
- Metadata support

### v2.1.0 (2025-10-30)
- Excel export improvements
- Color-coding by depth

### v2.0.0 (2025-10-29)
- Core refactoring
- API introduction
- Test suite

## Support and Documentation

- **User Guide**: [docs/USER_GUIDE.md](docs/USER_GUIDE.md)
- **API Reference**: [docs/API_REFERENCE.md](docs/API_REFERENCE.md)
- **Docker Guide**: [docs/DOCKER.md](docs/DOCKER.md)
- **ETA Mode**: [docs/ETA_MODE.md](docs/ETA_MODE.md)
- **Changelog**: [CHANGELOG.md](CHANGELOG.md)

## License

This project is licensed under the BSD-2 License - see the LICENSE file for details.

## Contact

For issues, questions, or contributions, please visit the GitHub repository:
https://github.com/Gertrud-Violett/FTA_Editor
