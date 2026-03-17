# Publishing pyscid to PyPI

This guide covers how to publish the pyscid package to PyPI.

## Prerequisites

1. **PyPI Account**
   - Create account at https://pypi.org/account/register/
   - Create account at https://test.pypi.org/account/register/ (for testing)

2. **API Tokens**
   - Generate API token at https://pypi.org/manage/account/token/
   - Generate test token at https://test.pypi.org/manage/account/token/
   - Save tokens securely (you'll need them for upload)

3. **Install Build Tools**
   ```bash
   pip install --upgrade build twine
   ```

## Pre-Publishing Checklist

- [ ] All tests passing
- [ ] README.md is up to date
- [ ] Version number updated in:
  - [ ] `pyproject.toml`
  - [ ] `pyscid/__init__.py`
- [ ] CHANGELOG or release notes prepared
- [ ] All changes committed to git
- [ ] Branch merged to main (if on feature branch)
- [ ] Git tag created for version

## Step 1: Update Version

Update version in two places:

**pyproject.toml:**
```toml
version = "0.1.0"  # Update this
```

**pyscid/__init__.py:**
```python
__version__ = "0.1.0"  # Update this
```

## Step 2: Clean Previous Builds

```bash
cd /home/e/Documents/Projects/scidPython
rm -rf dist/ build/ *.egg-info
```

## Step 3: Build the Package

```bash
python3 -m build
```

This creates:
- `dist/pyscid-0.1.0.tar.gz` (source distribution)
- `dist/pyscid-0.1.0-py3-none-any.whl` (wheel distribution)

## Step 4: Check the Package

```bash
twine check dist/*
```

Should show:
```
Checking dist/pyscid-0.1.0.tar.gz: PASSED
Checking dist/pyscid-0.1.0-py3-none-any.whl: PASSED
```

## Step 5: Test Upload (Optional but Recommended)

Upload to TestPyPI first:

```bash
twine upload --repository testpypi dist/*
```

Enter your TestPyPI API token when prompted:
- Username: `__token__`
- Password: `pypi-...` (your test token)

Test installation from TestPyPI:
```bash
pip install --index-url https://test.pypi.org/simple/ pyscid
```

## Step 6: Upload to PyPI

Once verified on TestPyPI:

```bash
twine upload dist/*
```

Enter your PyPI API token when prompted:
- Username: `__token__`
- Password: `pypi-...` (your production token)

## Step 7: Verify Installation

```bash
# In a fresh environment
pip install pyscid

# Test it works
python -c "from pyscid import Database; print('✓ pyscid installed successfully')"
```

## Step 8: Create GitHub Release

1. Go to https://github.com/zaderrr/pyscid/releases
2. Click "Create a new release"
3. Create tag: `v0.1.0`
4. Release title: `v0.1.0 - Initial Release`
5. Add release notes describing changes
6. Publish release

## Using API Tokens

Instead of entering credentials each time, configure them:

**~/.pypirc:**
```ini
[distutils]
index-servers =
    pypi
    testpypi

[pypi]
username = __token__
password = pypi-YOUR_PRODUCTION_TOKEN_HERE

[testpypi]
repository = https://test.pypi.org/legacy/
username = __token__
password = pypi-YOUR_TEST_TOKEN_HERE
```

Then upload with:
```bash
twine upload dist/*  # Uses token from ~/.pypirc
```

## Troubleshooting

**Error: "File already exists"**
- You cannot re-upload the same version
- Increment version number and rebuild

**Error: "Invalid package name"**
- Package name must be unique on PyPI
- Check if name is already taken: https://pypi.org/project/pyscid/

**Error: "Long description has syntax errors"**
- Run: `twine check dist/*`
- Fix any Markdown/RST issues in README.md

**Error: "Missing files in distribution"**
- Check MANIFEST.in includes all needed files
- Rebuild with `python3 -m build`

## Quick Reference

```bash
# Full publish workflow
cd /home/e/Documents/Projects/scidPython

# 1. Clean
rm -rf dist/ build/ *.egg-info

# 2. Update version numbers in pyproject.toml and __init__.py

# 3. Build
python3 -m build

# 4. Check
twine check dist/*

# 5. Test upload (optional)
twine upload --repository testpypi dist/*

# 6. Production upload
twine upload dist/*

# 7. Verify
pip install pyscid
python -c "from pyscid import Database; print('✓ Works!')"
```

## After Publishing

1. Update version to next development version (e.g., `0.1.1-dev`)
2. Create announcement on GitHub Discussions or Reddit
3. Share on chess programming communities
4. Monitor issues and feedback

## Version Numbering

Follow semantic versioning (semver):
- `0.1.0` → `0.1.1` - Bug fixes
- `0.1.0` → `0.2.0` - New features (backwards compatible)
- `0.1.0` → `1.0.0` - Major release or breaking changes

Current version: **0.1.0** (initial release)
