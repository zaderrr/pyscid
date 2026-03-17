#!/bin/bash
# Build script for pyscid package

set -e  # Exit on error

echo "========================================"
echo "Building pyscid package for PyPI"
echo "========================================"
echo

# Check we're in the right directory
if [ ! -f "pyproject.toml" ]; then
    echo "Error: pyproject.toml not found. Run from project root."
    exit 1
fi

# Clean previous builds
echo "1. Cleaning previous builds..."
rm -rf dist/ build/ *.egg-info pyscid.egg-info
echo "   ✓ Cleaned"
echo

# Check version consistency
echo "2. Checking version consistency..."
PYPROJECT_VERSION=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
INIT_VERSION=$(grep '__version__ = ' pyscid/__init__.py | sed 's/__version__ = "\(.*\)"/\1/')

echo "   pyproject.toml: $PYPROJECT_VERSION"
echo "   __init__.py:    $INIT_VERSION"

if [ "$PYPROJECT_VERSION" != "$INIT_VERSION" ]; then
    echo "   ✗ Version mismatch!"
    echo "   Please update versions to match in both files."
    exit 1
fi
echo "   ✓ Versions match: $PYPROJECT_VERSION"
echo

# Install/upgrade build tools
echo "3. Checking build tools..."
python3 -m pip install --upgrade build twine -q
echo "   ✓ Build tools ready"
echo

# Build the package
echo "4. Building package..."
python3 -m build
echo "   ✓ Package built"
echo

# List created files
echo "5. Created distribution files:"
ls -lh dist/
echo

# Check package
echo "6. Checking package with twine..."
twine check dist/*
echo

echo "========================================"
echo "✓ Build complete!"
echo "========================================"
echo
echo "Distribution files ready in dist/"
echo
echo "Next steps:"
echo "  - Test upload:       twine upload --repository testpypi dist/*"
echo "  - Production upload: twine upload dist/*"
echo
echo "See PUBLISHING.md for detailed instructions."
