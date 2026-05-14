# Contributing to SYNAPSE Adapter SDK

Thank you for your interest in contributing. This document explains how
to contribute and what is required for a contribution to be accepted.

## Developer Certificate of Origin (DCO)

Every commit to this repository must carry a DCO sign-off. By adding the sign-off
you certify that you have the right to submit the contribution under the MIT license
and that you accept the [Developer Certificate of Origin v1.1](https://developercertificate.org/).

Add the sign-off with the `-s` flag:

```bash
git commit -s -m "feat: your commit message"
```

This adds `Signed-off-by: Your Name <you@example.com>` to the commit body. The DCO
check GitHub Action will block the PR if any commit in the branch is missing a sign-off.
If you forgot to sign off an existing commit, amend it:

```bash
git commit --amend -s --no-edit
git push --force-with-lease
```

## Reproducible builds

The project uses `uv` for dependency management. All direct and transitive dependencies
are pinned in `uv.lock` (committed to the repository). To reproduce the exact build
environment used in CI:

```bash
uv sync --frozen --all-extras --dev
```

`--frozen` fails if `uv.lock` is out of date, ensuring the installed environment exactly
matches the lock file. Never use `uv sync` without `--frozen` in release or verification
contexts.

To verify a release wheel:

```bash
uv build
# The .whl in dist/ is reproducible given the same Python version and uv.lock
```

## Ways to contribute

- Write a new adapter for a model not yet in the ecosystem
- Fix a bug in the SDK
- Improve documentation
- Add or improve tests
- Report issues at https://github.com/synapse-ir/adapter-sdk/issues

Issues labelled **`good first issue`** are intentionally scoped to be approachable for new contributors. Issues labelled **`help wanted`** are where additional hands are most needed. Both labels are searchable at https://github.com/synapse-ir/adapter-sdk/labels.

## Requirements for acceptable contributions

All pull requests must meet these requirements before they will be merged:

### Code style
- Python code must pass ruff formatting and linting with no errors
- Python code must pass mypy type checking with no errors
- Run both with: uv run ruff check . && uv run mypy src/

### Tests
- All existing tests must pass: uv run pytest tests/ -v
- New functionality must include tests
- Test coverage must not decrease

### Adapter contributions
- The adapter must pass all 13 validation rules:
  synapse-validate --adapter your_module.YourAdapter
- The adapter must pass all 20 standard fixtures:
  synapse-validate --adapter your_module.YourAdapter --all-fixtures
- The adapter must include a test suite using mock model output
- No real model inference calls in tests

### Pull request process
1. Fork the repository
2. Create a branch: git checkout -b feat/your-adapter-name
3. Make your changes
4. Run the full test suite and validator
5. Open a pull request with a clear description of what the adapter does
   and which model it wraps
6. A maintainer will review within 14 days

### Code review standards

Every pull request must receive at least one approval from a Maintainer who is not the PR author before merging. Reviewers verify:

- All CI checks pass (ruff, mypy, pytest with ≥80% branch coverage)
- New functionality includes tests and does not reduce coverage
- Public API changes have docstrings and type hints
- Adapter contributions pass `synapse-validate --all-fixtures`
- The DCO sign-off is present on every commit in the branch
- No secrets, credentials, or personally identifiable information are introduced
- Code matches the coding standards in this document

Reviewers leave comments using the GitHub review interface. A PR may not be merged until all blocking comments are resolved and at least one approving review is recorded. The PR author may not self-approve. See GOVERNANCE.md for the full decision process.

## Coding standards

- Python 3.11 or higher required
- All public functions and classes must have docstrings
- Type hints are required on all function signatures
- Adapter functions must be pure — no network calls, no side effects,
  no persistent state (enforced by the NO_NETWORK_CALLS validator rule)

## Two-factor authentication

Maintainers with write access to any repository in the `synapse-ir` GitHub organisation **must** enable two-factor authentication (2FA) on their GitHub account. The organisation enforces this requirement at the settings level; accounts without 2FA will be removed from the organisation until the requirement is met.

Use a cryptographic 2FA method — a hardware security key (FIDO2/WebAuthn) or a TOTP authenticator app. SMS-only 2FA is not accepted.

## Code of Conduct

All contributors are expected to follow the project Code of Conduct.
Reports of violations can be sent to the maintainer via GitHub.
