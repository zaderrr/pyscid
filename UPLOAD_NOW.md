# Upload to PyPI - Quick Start

## ✅ Status: READY TO UPLOAD

Your package is built and tested. Follow these steps to publish.

## 1️⃣ One-Time Setup (if not done)

### Create PyPI Account
Visit: https://pypi.org/account/register/

### Generate API Token
1. Go to: https://pypi.org/manage/account/token/
2. Click "Add API token"
3. Token name: "pyscid-upload"
4. Scope: "Entire account" (or specific to this project later)
5. **SAVE THE TOKEN** - you won't see it again!

## 2️⃣ Upload to PyPI

```bash
cd /home/e/Documents/Projects/scidPython
twine upload dist/*
```

When prompted:
```
Enter your username: __token__
Enter your password: pypi-xxxxxxxxxx  # Paste your token here
```

## 3️⃣ Verify Upload

After successful upload, check:
- Your package page: https://pypi.org/project/pyscid/
- Try installing: `pip install pyscid`

## 🧪 Optional: Test on TestPyPI First

If you want to test the upload process without affecting the main PyPI:

### Setup TestPyPI
1. Create account: https://test.pypi.org/account/register/
2. Generate token: https://test.pypi.org/manage/account/token/

### Upload to TestPyPI
```bash
twine upload --repository testpypi dist/*
```

### Test Installation
```bash
pip install --index-url https://test.pypi.org/simple/ pyscid
```

## 📋 Pre-Upload Checklist

Before running `twine upload`:

- [ ] Email correct in pyproject.toml? (line 10)
- [ ] Ready to publish version 0.1.0? (cannot change after upload)
- [ ] All changes committed to git?
- [ ] Git tag created? `git tag -a v0.1.0 -m "Release v0.1.0"`

## 🚨 Important Notes

1. **Cannot re-upload same version** - If you upload 0.1.0, you cannot replace it. Must use 0.1.1 for any fixes.

2. **Email will be public** - Update `pyproject.toml` line 10 if needed:
   ```toml
   authors = [
       {name = "zaderrr", email = "your.email@example.com"}
   ]
   ```

3. **Token security** - Never commit your API token to git!

## 🎯 After Upload

Once uploaded successfully:

### Create GitHub Release
```bash
# Push the tag
git push origin v0.1.0

# Or create release on GitHub:
# https://github.com/zaderrr/pyscid/releases/new
```

### Share the News
- Announce on GitHub Discussions
- Share on chess programming forums
- Tweet about it (optional)

### Monitor
- Watch for issues: https://github.com/zaderrr/pyscid/issues
- Check download stats: https://pypistats.org/packages/pyscid

## 🔧 Troubleshooting

### "The user '__token__' isn't allowed to upload"
- Make sure you're using `__token__` as the username (with two underscores)
- Make sure token starts with `pypi-`

### "File already exists"
- You've already uploaded this version
- Must increment version and rebuild

### "HTTPError: 403 Forbidden"
- Token might be expired or invalid
- Generate a new token

### "Package name already taken"
- Someone else registered `pyscid`
- Try a different name in pyproject.toml

## ✨ Ready to Publish!

Your package is ready. Just run:

```bash
twine upload dist/*
```

The world awaits your chess database library! 🎉♟️
