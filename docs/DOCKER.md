# Docker Deployment Guide

Run FTA/ETA Editor in Docker containers for easy deployment and isolation.

**Current Version**: 2.2.2  
**Last Updated**: November 6, 2025

## What's New in v2.2.2

- **UI Improvements**: Probabilities display side by side, improved text visibility
- **New Features**: Hide zero probability nodes, "New Analysis" button
- **Fixed**: Graph UI bug preserving FTA tree and graph view order

## Quick Start

```bash
# Clone the repository
git clone https://github.com/Gertrud-Violett/FTA_Editor.git
cd FTA_Editor

# Build and run with Docker Compose
docker-compose up

# Or build manually
docker build -t fta-editor:2.2.2 .
docker run -it --rm fta-editor:2.2.2
```

## Docker Compose (Recommended)

### File: `docker-compose.yml`

```yaml
version: '3.8'

services:
  fta-editor:
    build: .
    image: fta-editor:latest
    container_name: fta_editor_app
    environment:
      - DISPLAY=${DISPLAY}
    volumes:
      - ./data:/app/data
      - ./output:/app/output
      - /tmp/.X11-unix:/tmp/.X11-unix:rw
    network_mode: host
    stdin_open: true
    tty: true
```

### Usage

```bash
# Start application
docker-compose up

# Run in background
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

## Dockerfile

### Base Image

Uses `python:3.9-slim` for small footprint.

### Key Features

- Installs Python dependencies
- Installs Graphviz for diagram visualization
- Sets up X11 for GUI display
- Configures non-root user
- Mounts data and output volumes

### Build Arguments

```bash
# Build with custom Python version
docker build --build-arg PYTHON_VERSION=3.10 -t fta-editor .
```

## X11 Display Setup

### Linux

```bash
# Allow X11 connections
xhost +local:docker

# Run with display
docker-compose up
```

### macOS

```bash
# Install XQuartz
brew install --cask xquartz

# Start XQuartz and enable network connections
# Applications → Utilities → XQuartz → Preferences → Security
# Check "Allow connections from network clients"

# Get IP
IP=$(ifconfig en0 | grep inet | awk '$1=="inet" {print $2}')

# Allow X11
xhost + $IP

# Run with display
DISPLAY=$IP:0 docker-compose up
```

### Windows

```bash
# Install VcXsrv or Xming

# Start X server with:
# - Multiple windows
# - Display number 0
# - Disable access control

# Set display
set DISPLAY=host.docker.internal:0

# Run
docker-compose up
```

## Volume Mounts

### Data Directory

Mount for input files:
```bash
-v $(pwd)/data:/app/data
```

### Output Directory

Mount for exports:
```bash
-v $(pwd)/output:/app/output
```

### Configuration

Mount for custom config:
```bash
-v $(pwd)/config:/app/config
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DISPLAY` | `:0` | X11 display |
| `FTA_MODE` | `FTA` | Default mode |
| `LOG_LEVEL` | `INFO` | Logging level |

## Production Deployment

### Docker Image

Build production image:
```bash
docker build -t fta-editor:prod \
  --build-arg ENV=production \
  -f Dockerfile.prod .
```

### Docker Hub

```bash
# Tag
docker tag fta-editor:latest username/fta-editor:latest

# Push
docker push username/fta-editor:latest

# Pull and run
docker pull username/fta-editor:latest
docker run -it --rm username/fta-editor:latest
```

### Kubernetes

Deploy to Kubernetes:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: fta-editor
spec:
  replicas: 1
  selector:
    matchLabels:
      app: fta-editor
  template:
    metadata:
      labels:
        app: fta-editor
    spec:
      containers:
      - name: fta-editor
        image: username/fta-editor:latest
        ports:
        - containerPort: 8080
        volumeMounts:
        - name: data
          mountPath: /app/data
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: fta-data-pvc
```

## Headless Mode

Run without GUI (for batch processing):

```bash
docker run -it --rm \
  -v $(pwd)/data:/app/data \
  fta-editor \
  python scripts/batch_process.py
```

## Multi-Architecture Support

Build for multiple platforms:

```bash
# Setup buildx
docker buildx create --use

# Build multi-arch
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t username/fta-editor:latest \
  --push .
```

## Troubleshooting

### GUI Not Displaying

```bash
# Check X11 connection
echo $DISPLAY

# Test with xeyes
docker run -it --rm \
  -e DISPLAY=$DISPLAY \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  debian:latest \
  sh -c "apt-get update && apt-get install -y x11-apps && xeyes"
```

### Permission Errors

```bash
# Fix X11 permissions
xhost +local:docker

# Fix file permissions
chmod -R 755 data/
```

### Container Exits Immediately

```bash
# Check logs
docker-compose logs

# Run interactively
docker-compose run fta-editor /bin/bash
```

## Security Considerations

1. **Non-root user**: Container runs as user `appuser`
2. **Read-only root**: Use `--read-only` flag
3. **Resource limits**: Set memory/CPU limits in docker-compose
4. **Network isolation**: Use custom networks
5. **Secrets**: Use Docker secrets for sensitive data

Example with security hardening:
```yaml
services:
  fta-editor:
    build: .
    read_only: true
    user: "1000:1000"
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    tmpfs:
      - /tmp
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
```

## Performance Optimization

1. **Multi-stage builds**: Reduce image size
2. **Layer caching**: Order Dockerfile commands efficiently
3. **Slim base images**: Use alpine or slim variants
4. **Dependency optimization**: Install only required packages

## Monitoring

### Health Check

Add to Dockerfile:
```dockerfile
HEALTHCHECK --interval=30s --timeout=3s \
  CMD python -c "import sys; sys.exit(0)" || exit 1
```

### Logging

```bash
# View logs
docker-compose logs -f fta-editor

# Save logs
docker-compose logs > fta-editor.log
```

---

For more details, see [README.md](../README.md) and [User Guide](USER_GUIDE.md).
