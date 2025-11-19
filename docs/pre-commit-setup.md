# Pre-commit Hooks Setup

Pre-commit hooks automatically check and format code before commits, ensuring code quality and consistency.

## Installation

Using `uv` (recommended):
```bash
# Install uv: https://github.com/astral-sh/uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install pre-commit and dependencies
uv pip install -r requirements.txt
```

Using `pip`:
```bash
# Install pre-commit
pip install pre-commit

# Or add to requirements.txt and install
pip install -r requirements.txt
```

## Setup

```bash
# Install git hooks
pre-commit install

# Install hooks for commit messages (optional)
pre-commit install --hook-type commit-msg
```

## Usage

### Automatic (Recommended)

Pre-commit hooks run automatically on `git commit`. If checks fail, the commit is blocked until issues are fixed.

```bash
git add .
git commit -m "Your commit message"
# Hooks run automatically
```

### Manual

Run hooks manually on all files:

```bash
# Run on all files
pre-commit run --all-files

# Run specific hook
pre-commit run black --all-files
pre-commit run pylint --all-files
```

### Skip Hooks (Not Recommended)

**When to skip:** Only when absolutely necessary (e.g., emergency fixes, fixing hook configuration itself, or when hooks are incorrectly blocking valid code).

```bash
# Skip hooks for a single commit
git commit --no-verify -m "Your commit message"

# Alternative: use -n flag (shorthand)
git commit -n -m "Your commit message"
```

**Warning:** Skipping hooks bypasses code quality checks. Always fix issues and re-run hooks afterward:
```bash
# After skipping, manually run hooks to verify
pre-commit run --all-files
```

## Configured Hooks

### Code Formatting
- **black** - Python code formatter (line length: 100)
- **isort** - Python import sorter (black-compatible)
- **prettier** - YAML formatter

### Code Quality
- **pylint** - Python linter
- **mypy** - Python type checker
- **shellcheck** - Shell script linter

### File Checks
- **trailing-whitespace** - Removes trailing whitespace
- **end-of-file-fixer** - Ensures files end with newline
- **check-yaml** - Validates YAML syntax
- **check-json** - Validates JSON syntax
- **check-added-large-files** - Prevents large file commits (>1MB)
- **check-merge-conflict** - Detects merge conflict markers
- **mixed-line-ending** - Normalizes line endings (LF)

## Updating Hooks

```bash
# Update hook versions
pre-commit autoupdate

# Reinstall hooks after update
pre-commit install --overwrite
```

## CI/CD Integration

Pre-commit can also run in CI/CD pipelines:

```yaml
# .github/workflows/pre-commit.yml (optional)
- name: Run pre-commit
  run: |
    pip install pre-commit
    pre-commit run --all-files
```

## Troubleshooting

### Hooks Not Running

```bash
# Verify hooks are installed
ls -la .git/hooks/pre-commit

# Reinstall if missing
pre-commit install --overwrite
```

### Hook Failures

If a hook fails:
1. Review the error message
2. Fix the issues manually, or
3. Let the hook auto-fix (if supported): `pre-commit run --all-files`

### Skip Specific Files

Add to `.pre-commit-config.yaml`:
```yaml
exclude: ^(path/to/exclude|another/path)
```

## Best Practices

1. **Run before committing:** Let hooks run automatically
2. **Fix issues immediately:** Don't skip hooks unless absolutely necessary
3. **Update regularly:** Run `pre-commit autoupdate` periodically
4. **Team alignment:** Ensure all team members have pre-commit installed

