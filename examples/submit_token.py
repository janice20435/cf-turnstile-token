"""Example: obtain a token and submit it using only the standard library."""

import os
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cf_turnstile_token import solve  # noqa: E402

API_KEY = os.environ.get("PEAK_API_KEY", "")
SITEKEY = "0x4AAAAAAAxxxx"
TARGET_URL = "https://example.com/"
FORM_URL = "https://example.com/submit"


def main():
    # 1. Get a fresh token from Peak.
    result = solve(API_KEY, SITEKEY, TARGET_URL)
    print("token:", result.token[:24], "...")

    # 2. Inject it as the cf-turnstile-response field.
    body = urlencode({"cf-turnstile-response": result.token, "payload": "hello"}).encode()
    req = Request(FORM_URL, data=body, method="POST")
    with urlopen(req, timeout=30) as resp:
        print("submit status:", resp.status)


if __name__ == "__main__":
    main()
