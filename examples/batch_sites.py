"""Example: batch-obtain tokens for a list of sites (pipeline friendly).

Usage:
    python examples/batch_sites.py https://example.com/ https://example.org/
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cf_turnstile_token import extract_sitekey, read_page, solve  # noqa: E402

API_KEY = os.environ.get("PEAK_API_KEY", "")


def main(urls):
    tokens = {}
    for url in urls:
        html = read_page(url)
        sitekey = extract_sitekey(html)
        if not sitekey:
            print(f"skip {url}: no sitekey")
            continue
        result = solve(API_KEY, sitekey, url)
        tokens[url] = result.token
        print(f"ok {url}")
    print(json.dumps(tokens, indent=2))


if __name__ == "__main__":
    main(sys.argv[1:] or ["https://example.com/"])
