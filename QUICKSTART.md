# Quick Start Guide

Get up and running with FTA/ETA Editor in 3 steps.

**Version**: 2.2.2 (Updated: November 6, 2025)

## 1. Install

**Prerequisites:** Python 3.8+ and [Graphviz](https://graphviz.org/download/)

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
docker build -t fta-editor:2.2.2 .
docker run -it --rm fta-editor:2.2.2
```

## What's New in v2.2.2

- ✅ UI improvements: Probabilities display side by side for space efficiency
- ✅ New features: Hide zero probability nodes, "New Analysis" button
- ✅ Fixed: Graph UI bug preserving FTA tree and graph view order
- ✅ Enhanced: Improved node visibility and diagram resolution

## Need Help?

- Load example: `data/examples/sampleFTA.json`
- Documentation: `docs/USER_GUIDE.md`
- Deployment guide: `DEPLOYMENT.md`
- Test installation: `python -m pytest tests/`