# Contributing to FTA/ETA Editor

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help others learn and grow

## How to Contribute

### Reporting Bugs

1. Check if the bug has already been reported in [Issues](https://github.com/Gertrud-Violett/FTA_editor/issues)
2. If not, create a new issue with:
   - Clear title and description
   - Steps to reproduce
   - Expected vs actual behavior
   - Screenshots if applicable
   - System information (OS, Python version)

### Suggesting Features

1. Check if the feature has been suggested in [Issues](https://github.com/Gertrud-Violett/FTA_editor/issues)
2. Create a new issue describing:
   - The problem it solves
   - Proposed solution
   - Alternative approaches considered
   - Examples of usage

### Pull Requests

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Make your changes
4. Add or update tests
5. Update documentation
6. Commit your changes (`git commit -m 'Add AmazingFeature'`)
7. Push to branch (`git push origin feature/AmazingFeature`)
8. Open a Pull Request

## Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/FTA_editor.git
cd FTA_editor

# Install dependencies -- with uv (recommended) or plain pip
uv sync --extra dev
pip install -r requirements.txt -r fta_web/requirements.txt pytest pyinstaller  # pip alternative

# Run tests
uv run pytest fta_web/tests/ desktop/tests/   # or: python -m pytest (pytest.ini lists both)

# Run an application
uv run python fta_web/run.py                  # web app -- the primary path
uv run python desktop/src/FTA_Editor_UI.py    # legacy desktop app -- backup/fallback, frozen
```

The web app (`fta_web/`) is where all new work goes. `desktop/` holds the
original Tkinter application and its test suite as a fallback; its `src/` is
hash-pinned by `fta_web/tests/test_vendor_integrity.py` and must not be edited
(see `fta_web/core/DIVERGENCE.md`).

`uv sync --extra dev` installs everything: both apps' optional features, plus
`pytest` and `pyinstaller`. See `pyproject.toml` for the full extras list
(`web`, `desktop`, `excel`, `ai`, `test`, `build`, `all`, `dev`) if you only
need a subset.

## Coding Standards

### Python Style

- Follow PEP 8
- Use meaningful variable names
- Add docstrings to functions and classes
- Keep functions focused and small
- Maximum line length: 100 characters

Example:
```python
def calculate_probability(node, mode="FTA"):
    """
    Calculate probability for a node.
    
    Args:
        node (dict): Node data structure
        mode (str): "FTA" or "ETA"
        
    Returns:
        float: Calculated probability
    """
    # Implementation here
    pass
```

### Testing

- Write tests for new features
- Maintain test coverage above 80%
- Use descriptive test names
- Test edge cases

Example:
```python
def test_eta_mode_calculation():
    """Test ETA mode calculates probabilities top-down."""
    core = FTACore()
    core.set_metadata(mode="ETA")
    # ... test implementation
    assert result == expected
```

### Documentation

- Update README.md for user-facing changes
- Update docs/ for API changes
- Add inline comments for complex logic
- Include examples in docstrings

## Testing Guidelines

### Running Tests

```bash
# All tests (web app + legacy desktop suite)
python -m pytest

# Web app only
python -m pytest fta_web/tests/

# Legacy desktop suite only
python -m pytest desktop/tests/
python desktop/tests/test_core_module.py      # a single file, the old way

# With coverage
python -m pytest fta_web/tests/ --cov=fta_web --cov-report=html
```

### Writing Tests

- Use pytest framework
- One test file per source file
- Name tests clearly: `test_<feature>_<scenario>`
- Use fixtures for common setup
- Test both success and error cases

## Documentation

### Required Documentation

- README.md - Overview and quick start
- API changes - Update docs/API_REFERENCE.md
- New features - Update docs/USER_GUIDE.md
- Docstrings - All public functions/classes

### Documentation Style

- Clear and concise
- Include examples
- Use proper markdown formatting
- Add diagrams where helpful

## Commit Messages

Use clear, descriptive commit messages:

```
Add feature: Brief description

- Detailed point 1
- Detailed point 2

Fixes #123
```

Format:
- First line: Summary (max 50 chars)
- Blank line
- Detailed description
- Reference issues/PRs

## Review Process

1. Automated checks must pass
2. Code review by maintainer
3. Address feedback
4. Approval and merge

## Release Process

1. Update `version` in `pyproject.toml`
2. Update CHANGELOG.md
3. Create release tag

## Questions?

- Open an issue for questions
- Join discussions in Issues
- Contact maintainers

## License

By contributing, you agree that your contributions will be licensed under the BSD2 License.

---

Thank you for contributing to FTA/ETA Editor!
