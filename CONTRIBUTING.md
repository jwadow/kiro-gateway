# Contributing to Kiro Gateway

Thanks for your interest in contributing!

## Philosophy

Kiro Gateway is a **transparent proxy** - we fix API-level issues while preserving user intent. When solving problems, we build systems that handle entire classes of issues, not one-off patches. We test paranoidly (happy path + edge cases + error scenarios), write clean code (type hints, docstrings, logging), and make errors actionable for users.

## Getting Started

1. Fork and clone the repo
2. Install dependencies: `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and configure
4. Run tests: `pytest -v`

## Development Workflow

```bash
# Create a branch
git checkout -b fix/your-fix
# or
git checkout -b feat/your-feature

# Make changes and test
pytest -v

# Commit (Conventional Commits format)
git commit -m "fix(scope): description"

# Push and open PR
git push origin your-branch
```

## Standards

- **English only** - All code, comments, docstrings, and variable names must be in English (except for specific cases like Unicode tests or multilingual examples)
- **Type hints** - All functions must be typed
- **Docstrings** - Google style with Args/Returns/Raises
- **Logging** - Use loguru at key decision points
- **Error handling** - Catch specific exceptions, add context
- **No tech debt** - Clean up hardcoded values and duplication immediately
- **Complete consistency** - Changes must be applied to BOTH OpenAI and Anthropic APIs, and to BOTH streaming and non-streaming modes
- **Tests required** - Every commit must include comprehensive tests (edge cases, error scenarios, not just happy path). Check `tests/README.md` to find the appropriate existing `test_*.py` file

## Pull Requests

**Your PR quality reflects your engagement with the project.** PRs without tests, with non-English code, or missing consistency across architecture suggest a quick hack and fix rather than thoughtful contribution. We review all PRs, but those demonstrating care for code quality, comprehensive testing, and architectural understanding receive priority attention and faster merges.

**Before submitting:**
- Tests pass (including edge cases)
- Code follows project style
- Error messages are user-friendly
- No placeholders or TODOs
- Changes are focused. Don't mix functional changes with mass formatting/whitespace fixes across many files

**PR should include:**
- Clear description of what and why
- Link to related issue
- Test coverage summary

**Keep it reviewable:**
- If fixing formatting, limit it to files you're actually changing
- Avoid auto-formatter changes across the entire codebase in the same PR as functional changes

## CLA

All contributors must sign the Contributor License Agreement (automated via bot).

## Questions?

- **Bug reports:** [Open an issue](https://github.com/jwadow/kiro-gateway/issues)
- **Feature ideas:** Discuss in an issue first
- **Questions:** [Start a discussion](https://github.com/jwadow/kiro-gateway/discussions)

## Recognition

Contributors are listed in [`CONTRIBUTORS.md`](CONTRIBUTORS.md).

---

**For detailed guidelines:** See [`AGENTS.md`](AGENTS.md)
