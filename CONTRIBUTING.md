# Contributing to ATEM Tally Server

Thank you for your interest in contributing! This document outlines how to get involved.

---

## Getting Started

### Prerequisites

- Python 3.10+
- pip
- Git
- Arduino (for personalized hawdware firmware only)

### Local Setup

```bash
git clone https://github.com/paulofernando1/ATEMTallyServer.git
cd ATEMTallyServer
pip install -r requirements.txt
python app.py
```

---

## Project Structure

├── app.py              # Entry point, main GUI (CustomTkinter)

├── static/             # Web assets served to tally clients

├── *.ico / *.png       # Application icons

└── requirements.txt

---

## How to Contribute

### Reporting Bugs

Open an issue with:
- OS and Python version
- Steps to reproduce
- Expected vs actual behavior
- Logs or screenshots if applicable

### Suggesting Features

Open an issue with the `enhancement` label describing:
- The use case
- How it fits the project scope (ATEM switcher tally signaling)

### Submitting Code

1. Fork the repository
2. Create a branch: `git checkout -b feature/your-feature-name`
3. Make your changes
4. Test locally (GUI + web tally client)
5. Commit with a clear message: `git commit -m "feat: describe your change"`
6. Push and open a Pull Request against `main`

---

## Code Guidelines

- Follow PEP 8
- Keep GUI logic in `app.py`, web logic in the Flask/server layer
- Use `resource_path()` for all file references (bundle compatibility)
- Avoid hardcoded paths or ports where configurable alternatives exist

---

## Commit Message Format

Use conventional commits where possible:

| Prefix | Use for |
|--------|---------|
| `feat:` | New feature |
| `fix:` | Bug fix |
| `docs:` | Documentation only |
| `refactor:` | Code restructure, no behavior change |
| `chore:` | Build, deps, tooling |

---

## Pull Request Checklist

- [ ] Tested on Windows (primary target platform)
- [ ] Icons and static assets load correctly in bundled `.exe`
- [ ] No hardcoded IPs or ports introduced
- [ ] PR description explains the change and motivation

---

## License

By contributing, you agree your code will be licensed under the same license as this project.
