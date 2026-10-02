# Contributing to Antigravity Bridge

Thank you for your interest in contributing to Antigravity Bridge! We welcome contributions to expand model compatibility, improve performance, add new platform integrations, and squash bugs.

## How to Contribute

### Reporting Issues
- Check existing issues before opening a new one.
- Provide clear reproduction steps, including operating system, Python version, active engine mode, and relevant error logs.

### Submitting Pull Requests
1. Fork the repository and create your branch from `main`:
   ```bash
   git checkout -b feat/your-feature-name
   ```
2. Set up your virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Or on Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Run tests to ensure nothing is broken:
   ```bash
   python -m pytest tests/
   ```
4. Commit your changes with clear, descriptive commit messages.
5. Push to your fork and submit a Pull Request targeting `main`.

## Code Guidelines
- Follow PEP 8 style guidelines.
- Keep route handlers modular and clean.
- Ensure all streaming responses adhere strictly to the OpenAI SSE protocol or Anthropic Messages API specs.
- Never commit private API keys, secrets, or personal paths.
