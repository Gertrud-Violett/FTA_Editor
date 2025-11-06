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

# Install dependencies
pip install -r requirements.txt

# Run tests
python -m pytest tests/

# Run application
python src/FTA_Editor_UI.py
```

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
# All tests
python -m pytest tests/

# Specific test file
python tests/test_core_module.py

# With coverage
python -m pytest tests/ --cov=src --cov-report=html
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

1. Update version in setup.py
2. Update CHANGELOG.md
3. Create release tag
4. Build and publish to PyPI

## Questions?

- Open an issue for questions
- Join discussions in Issues
- Contact maintainers

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing to FTA/ETA Editor!
