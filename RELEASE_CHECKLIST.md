# Release Checklist for pyscid

Use this checklist before publishing to PyPI.

## Pre-Release Checklist

### Code Quality
- [ ] All tests pass locally
- [ ] No lint errors or warnings
- [ ] Code formatted consistently
- [ ] All new features documented
- [ ] Examples work correctly

### Documentation
- [ ] README.md is complete and accurate
- [ ] API documentation is up to date
- [ ] CHANGELOG.md updated (if exists)
- [ ] All code examples tested

### Version Control
- [ ] All changes committed to git
- [ ] Working on correct branch (usually `main`)
- [ ] No uncommitted changes
- [ ] Branch pushed to remote

### Package Configuration
- [ ] Version number updated in:
  - [ ] `pyproject.toml` line 7
  - [ ] `pyscid/__init__.py` line 22
- [ ] Author email updated in `pyproject.toml` (if needed)
- [ ] Dependencies listed correctly
- [ ] License file present (LICENSE)
- [ ] README.md present

### Build & Test
- [ ] Clean build directory: `rm -rf dist/ build/ *.egg-info`
- [ ] Build succeeds: `./build_package.sh`
- [ ] Twine check passes
- [ ] Test installation in fresh venv
- [ ] Import and basic usage work

## Release Steps

### 1. Final Version Check
```bash
grep 'version' pyproject.toml pyscid/__init__.py
```
Ensure both show the same version number.

### 2. Create Git Tag
```bash
git tag -a v0.1.0 -m "Release version 0.1.0"
git push origin v0.1.0
```

### 3. Build Package
```bash
./build_package.sh
```

### 4. Test Upload to TestPyPI (Optional)
```bash
twine upload --repository testpypi dist/*
```

Test installation:
```bash
pip install --index-url https://test.pypi.org/simple/ pyscid
```

### 5. Upload to PyPI
```bash
twine upload dist/*
```

### 6. Verify Installation
```bash
# In a fresh environment
pip install pyscid
python -c "from pyscid import Database; print('✓ Works!')"
```

### 7. Create GitHub Release
1. Go to: https://github.com/zaderrr/pyscid/releases/new
2. Choose tag: `v0.1.0`
3. Release title: `v0.1.0 - Initial Release`
4. Add release notes
5. Attach dist files (optional)
6. Publish release

## Post-Release

- [ ] Announcement on GitHub Discussions
- [ ] Update version to next dev version (e.g., `0.1.1-dev`)
- [ ] Tweet/post about release (optional)
- [ ] Share in chess programming communities

## Quick Commands Reference

```bash
# Check current state
git status
git log --oneline -5

# Version check
grep version pyproject.toml pyscid/__init__.py

# Clean and build
rm -rf dist/ build/ *.egg-info
./build_package.sh

# Upload to TestPyPI
twine upload --repository testpypi dist/*

# Upload to PyPI
twine upload dist/*

# Create and push tag
git tag -a v0.1.0 -m "Release v0.1.0"
git push origin v0.1.0
```

## Version History

- v0.1.0 - Initial release with namebase interface and ID-based search
