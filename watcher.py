#!/usr/bin/env python3
"""Entry point: `python watcher.py`. See internwatch/cli.py for flags and env vars."""
import sys

from internwatch.cli import main

if __name__ == "__main__":
    sys.exit(main())
