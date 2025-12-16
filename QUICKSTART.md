# Quick Start Guide

Get up and running with FTA/ETA Editor in 3 steps.

**Version**: 1.5.0 (Updated: December 16, 2025)

## 1. Install

**Prerequisites:** Python 3.10+ and [Graphviz](https://graphviz.org/download/)

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

## AI Assistant Setup (Optional)

The AI assistant can analyze your FTA and suggest improvements.

1. **Get an API key** from [OpenAI Platform](https://platform.openai.com/)
2. **Click ⚙ (Settings)** in the AI Assistant panel
3. **Enter your API key** and click "Test & Save"
4. **Start chatting!** Ask questions or use quick actions

Your API key is stored locally at `~/.fta_editor/ai_credentials.json`, never in the repository.

See [README.md](README.md#ai-assistant-setup) for detailed setup instructions.

## What's New in v1.5.0

- ✅ **AI Assistant**: Integrated chat interface for FTA analysis
- ✅ **Smart Suggestions**: AI can propose new nodes and modifications
- ✅ **Change Confirmation**: Review and approve AI suggestions before applying
- ✅ **Secure Storage**: API credentials stored locally, outside repository
- ✅ **OpenAI Compatible**: Works with OpenAI, Azure OpenAI, and compatible APIs

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+N` | New analysis |
| `Ctrl+A` | Add node |
| `Ctrl+E` | Edit node |
| `Ctrl+D` | Delete node |
| `Ctrl+S` | Save |
| `Ctrl+R` | Render diagram |

## Need Help?

- Load example: `data/examples/sampleFTA.json`
- Documentation: `docs/USER_GUIDE.md`
- AI Setup: See [README.md](README.md#ai-assistant-setup)
- Test installation: `python -m pytest tests/`