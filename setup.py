#!/usr/bin/env python3

from distutils.core import setup
import os
import glob


setup(
    name="aiomatrix",
    version="0.0",
    description="Matrix client API for Python asyncio",
    long_description=(
        "API endpoint for the matrix.org protocol for async Python.\n"
        "Designed for writing GUI/TUI clients and bots.\n"
    ),
    maintainer="SFT Technologies",
    maintainer_email="jj@stusta.net",
    url="https://github.com/SFTtech/aiomatrix",
    license='LGPL3+',
    packages=[
        "aiomatrix",
    ],
    data_files=[],
    platforms=[
        'Linux',
    ],
    classifiers=[
        ("License :: OSI Approved :: "
         "GNU Lesser General Public License v3 or later (LGPLv3+)"),
        "Topic :: Internet :: WWW/HTTP",
        "Intended Audience :: Developers",
    ],
)
