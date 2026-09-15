"""Example: discover every Turnstile sitekey on a page.

Usage:
    python examples/find_sitekeys.py https://example.com/
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cf_turnstile_token import extract_sitekeys, read_page  # noqa: E402


def main(url):
    keys = extract_sitekeys(read_page(url))
    if not keys:
        print("no Turnstile sitekey found")
        return 2
    for key in keys:
        print(key)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "https://example.com/"))
