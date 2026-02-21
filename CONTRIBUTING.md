# Contributing to Loom

Thank you for your interest in contributing to Loom! 🧵

## Getting Started

1. Fork the repository
2. Clone your fork
3. Create a virtual environment: `python3 -m venv .venv`
4. Install dependencies: `.venv/bin/pip install chromadb`
5. Make sure Ollama is running with `nomic-embed-text`

## Development

### Running Tests

```bash
# Run the test suite
python -m pytest tests/

# Test a specific feature
loom --project test-dev extract < test_requirements.txt
loom --project test-dev list
```

### Code Style

- Follow PEP 8
- Use type hints where practical
- Keep functions focused and documented

## Submitting Changes

1. Create a feature branch: `git checkout -b feature/my-feature`
2. Make your changes
3. Add tests for new functionality
4. Update documentation if needed
5. Submit a pull request

## Reporting Issues

- Check existing issues first
- Include reproduction steps
- Provide relevant environment info (Python version, OS, Ollama version)

## Feature Requests

We welcome ideas! Please open an issue describing:
- The problem you're trying to solve
- Your proposed solution
- Any alternatives you've considered

## Code of Conduct

Be respectful, constructive, and inclusive. We're all here to make development better.
