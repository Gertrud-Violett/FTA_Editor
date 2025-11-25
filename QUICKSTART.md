# Quick Start Guide

Get up and running with FTA/ETA Editor in 3 steps.

**Version**: 1.4.2 (Updated: November 25, 2025)

## 1. Install

**Prerequisites:** Python 3.14+ and [Graphviz](https://graphviz.org/download/)

```bash
# Clone and install
git clone https://github.com/Gertrud-Violett/FTA_Editor.git
cd FTA_Editor
python install.py
```

Or manually:

```bash
pip install -r requirements.txt
python src/FTA_Editor_UI.py
```

## 2. Run

```bash
python src/FTA_Editor_UI.py
```

## 3. Use

1. **Create nodes**: Select root, click "Add Node"
2. **Set probabilities**: Edit node, enter probability (0-1)
3. **Set logic gates**: Choose AND or OR for non-leaf nodes
4. **Choose mode**: FTA (failure analysis) or ETA (event sequences)  
5. **View diagram**: Logic gates displayed inside node boxes
6. **Export**: Save as JSON/Excel/XML or render diagram

## Docker Option

```bash
# Quick start with Docker
docker-compose up

# Or build specific version
docker build -t fta-editor:1.4.2 .
docker run -it --rm fta-editor:1.4.2
```

## What's New in v1.4.2

- ✅ Session Persistence: Fixed state consistency issues with filesystem sessions for Render.com deployment
- ✅ Japanese Font Support: Embedded Noto Sans CJK JP for proper Japanese/Chinese/Korean character rendering
- ✅ Web Application: Browser-based interface with zoom/pan and resizable panels
- ✅ Diagram Auto-Refresh: Fixed automatic diagram updates in web interface
- ✅ Multi-User: Reliable session management across Gunicorn worker processes

## Need Help?

- Load example: `data/examples/sampleFTA.json`
- Documentation: `docs/USER_GUIDE.md`
- Deployment guide: `DEPLOYMENT.md`
- Test installation: `python -m pytest tests/`