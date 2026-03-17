#!/usr/bin/env python3
"""
Setup script for pyscid package.
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="pyscid",
    version="0.1.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="A Python library for reading SCID chess databases (.si4, .si5, .pgn)",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/pyscid",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GNU General Public License v2 (GPLv2)",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Games/Entertainment :: Board Games",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.8",
    install_requires=[],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-cov>=4.0",
        ],
    },
    keywords="chess, scid, pyscid, si4, si5, pgn, database, games",
)
