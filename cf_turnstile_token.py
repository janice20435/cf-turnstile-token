"""cf-turnstile-token: obtain Cloudflare Turnstile tokens from the command line.

Reads a Turnstile sitekey from a page (or takes it directly), submits the solve
task to the Peak API, and returns a valid ``cf-turnstile-response`` token ready
to inject into a request or a form.

Built for operators, QA pipelines, and integration engineers who want a
repeatable, scriptable token flow without running a browser.

Typical use::

    cf-turnstile-token --sitekey 0x4AAAAAAAxxxx --url https://example.com/

    cf-turnstile-token --page https://example.com/protected --url https://example.com/

Library use::

    from cf_turnstile_token import extract_sitekey, solve

    html = read_page("https://example.com/protected")
    result = solve(api_key, extract_sitekey(html), "https://example.com/")
    print(result.token)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional
from urllib.request import ProxyHandler, Request, build_opener, urlopen

__all__ = [
    "PeakError",
    "SolveResult",
    "build_payload",
    "extract_sitekey",
    "extract_sitekeys",
    "read_page",
    "solve",
    "solve_many",
    "main",
]

__version__ = "1.0.0"

DEFAULT_API_URL = "https://api.peak.fo/solve"
ENV_API_KEY = "PEAK_API_KEY"
DEFAULT_TIMEOUT = 30.0
SOLVE_TIMEOUT = 180.0
DEFAULT_RETRIES = 3

_UA = "cf-turnstile-token/" + __version__

_SITEKEY_RE = re.compile(
    r"""data-sitekey\s*=\s*["'](?P<attr>[^"']+)["']"""
    r"""|(?:sitekey|render)\s*[:=]\s*["'](?P<js>[^"']+)["']""",
    re.I,
)


class PeakError(RuntimeError):
    """Raised when a solve request fails or returns an error."""


@dataclass
class SolveResult:
    """One successful solve.

    Attributes:
        token: the ``cf-turnstile-response`` value.
        raw:   the full decoded API response.
        elapsed: seconds spent on the successful attempt (when measured).
    """

    token: str
    raw: Dict[str, object] = field(default_factory=dict)
    elapsed: float = 0.0


def read_page(url: str, timeout: float = DEFAULT_TIMEOUT,
              proxy: Optional[str] = None) -> str:
    """Fetch a page and return its text body.

    Args:
        url: page to fetch.
        timeout: request timeout in seconds.
        proxy: optional ``http://user:pass@ip:port`` proxy for the fetch.
    """
    req = Request(url, headers={"User-Agent": _UA})
    if proxy:
        opener = build_opener(ProxyHandler({"http": proxy, "https": proxy}))
        with opener.open(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def extract_sitekeys(html: str) -> List[str]:
    """Return every unique Turnstile sitekey found in a page, in order."""
    seen: List[str] = []
    for match in _SITEKEY_RE.finditer(html or ""):
        candidate = next((g for g in match.groups() if g), None)
        if not candidate:
            continue
        candidate = candidate.strip()
        if candidate and candidate not in seen:
            seen.append(candidate)
    return seen


def extract_sitekey(html: str) -> Optional[str]:
    """Return the first Turnstile sitekey found in a page, or ``None``."""
    keys = extract_sitekeys(html)
    return keys[0] if keys else None


def build_payload(
    sitekey: str,
    url: str,
    proxy: Optional[str] = None,
    action: Optional[str] = None,
    cdata: Optional[str] = None,
) -> Dict[str, object]:
    """Build the Peak solve payload (see https://peak.fo/docs/turnstile)."""
    payload: Dict[str, object] = {
        "task_type": "turnstiletask",
        "sitekey": sitekey,
        "url": url,
    }
    if proxy:
        payload["proxy"] = proxy
    if action:
        payload["action"] = action
    if cdata:
        payload["cdata"] = cdata
    return payload


def solve(
    api_key: str,
    sitekey: str,
    url: str,
    proxy: Optional[str] = None,
    action: Optional[str] = None,
    cdata: Optional[str] = None,
    api_url: str = DEFAULT_API_URL,
    timeout: float = SOLVE_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    verbose: bool = False,
) -> SolveResult:
    """Submit a Turnstile solve to Peak and return the token.

    Retries transient network/HTTP failures with a short backoff. Raises
    :class:`PeakError` when the solve itself fails or all retries are spent.
    """
    if not api_key:
        raise PeakError(
            "No API key. Set PEAK_API_KEY or pass --api-key "
            "(1,000 free solves to start at https://peak.fo)."
        )

    payload = build_payload(sitekey, url, proxy, action, cdata)
    body = json.dumps(payload).encode("utf-8")
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}

    last_err: Optional[Exception] = None
    for attempt in range(1, max(1, retries) + 1):
        started = time.time()
        req = Request(api_url, data=body, headers=headers, method="POST")
        try:
            with urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # network / HTTP / JSON
            last_err = exc
            if verbose:
                print(f"attempt {attempt}/{retries} failed: {exc}", file=sys.stderr)
            if attempt < retries:
                time.sleep(2 * attempt)
                continue
            raise PeakError(
                f"Peak request failed after {retries} attempts: {exc}"
            ) from exc

        if not data.get("success"):
            raise PeakError(str(data.get("error") or "Peak solve failed"))
        token = (data.get("data") or {}).get("token")
        if not token:
            raise PeakError("Peak response missing data.token")
        return SolveResult(token=token, raw=data, elapsed=time.time() - started)

    raise PeakError(f"Peak request failed: {last_err}")


def solve_many(
    api_key: str,
    jobs: Iterable[Dict[str, str]],
    api_url: str = DEFAULT_API_URL,
    retries: int = DEFAULT_RETRIES,
    verbose: bool = False,
) -> List[Dict[str, object]]:
    """Solve several (sitekey, url) pairs and return one result per job.

    Each job is a mapping with ``sitekey`` and ``url`` keys and optional
    ``proxy``, ``action`` and ``cdata`` keys. Failed jobs are reported with an
    ``error`` field instead of a token, so one bad URL never kills a batch.
    """
    results: List[Dict[str, object]] = []
    for job in jobs:
        item: Dict[str, object] = {"sitekey": job.get("sitekey"), "url": job.get("url")}
        try:
            result = solve(
                api_key,
                job["sitekey"],
                job["url"],
                proxy=job.get("proxy"),
                action=job.get("action"),
                cdata=job.get("cdata"),
                api_url=api_url,
                retries=retries,
                verbose=verbose,
            )
            item["token"] = result.token
        except PeakError as exc:
            item["error"] = str(exc)
        results.append(item)
    return results


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cf-turnstile-token",
        description="Obtain a Cloudflare Turnstile token via the Peak API.",
    )
    parser.add_argument("--sitekey", help="Turnstile sitekey (0x...)")
    parser.add_argument("--page", help="URL of a page to auto-extract the sitekey from")
    parser.add_argument("--url", help="Target page URL (must end with '/')")
    parser.add_argument("--proxy", help="Proxy in http://user:pass@ip:port format")
    parser.add_argument("--action", help="Optional Turnstile action value")
    parser.add_argument("--cdata", help="Optional Turnstile cdata value")
    parser.add_argument("--api-key", default=os.environ.get(ENV_API_KEY, ""),
                        help="Peak API key (default: PEAK_API_KEY environment variable)")
    parser.add_argument("--api-url", default=DEFAULT_API_URL,
                        help="Solve endpoint (default: %(default)s)")
    parser.add_argument("--output", choices=["text", "json"], default="text",
                        help="Print the raw token (text) or a JSON object")
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES,
                        help="Attempts on transient failure (default: %(default)s)")
    parser.add_argument("--timeout", type=float, default=SOLVE_TIMEOUT,
                        help="Solve timeout in seconds (default: %(default)s)")
    parser.add_argument("--list-sitekeys", action="store_true",
                        help="With --page: print every sitekey found and exit")
    parser.add_argument("--batch", metavar="FILE",
                        help="File with one target URL per line; solves each and prints JSON")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress output")
    parser.add_argument("--verbose", action="store_true", help="Verbose progress output")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    def say(msg: str) -> None:
        if not args.quiet:
            print(msg, file=sys.stderr)

    # --list-sitekeys: discovery only, no API key needed
    if args.list_sitekeys:
        if not args.page:
            parser.error("--list-sitekeys requires --page")
        html = read_page(args.page, timeout=args.timeout)
        keys = extract_sitekeys(html)
        if not keys:
            say(f"no Turnstile sitekey found on {args.page}")
            return 2
        for key in keys:
            print(key)
        return 0

    # --batch: solve a file of URLs one by one
    if args.batch:
        try:
            targets = [line.strip() for line in open(args.batch, encoding="utf-8")
                       if line.strip() and not line.startswith("#")]
        except OSError as exc:
            print(f"error: cannot read batch file: {exc}", file=sys.stderr)
            return 2
        jobs = []
        for target in targets:
            html = read_page(target, timeout=args.timeout, proxy=args.proxy)
            sitekey = extract_sitekey(html)
            if not sitekey:
                say(f"skip {target}: no sitekey")
                continue
            jobs.append({"sitekey": sitekey, "url": target})
        results = solve_many(args.api_key, jobs, api_url=args.api_url,
                             retries=args.retries, verbose=args.verbose)
        print(json.dumps(results, indent=2))
        return 0 if all("token" in r for r in results) else 1

    sitekey = args.sitekey
    if not sitekey and args.page:
        html = read_page(args.page, timeout=args.timeout, proxy=args.proxy)
        sitekey = extract_sitekey(html)
        if not sitekey:
            print(f"error: no Turnstile sitekey found on {args.page}", file=sys.stderr)
            return 2
        say(f"sitekey: {sitekey}")
    if not sitekey:
        parser.error("either --sitekey or --page is required")
    if not args.url:
        parser.error("--url is required (target page URL, ending with '/')")

    try:
        result = solve(
            args.api_key,
            sitekey,
            args.url,
            proxy=args.proxy,
            action=args.action,
            cdata=args.cdata,
            api_url=args.api_url,
            timeout=args.timeout,
            retries=args.retries,
            verbose=args.verbose,
        )
    except PeakError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.output == "json":
        print(json.dumps({"token": result.token, "success": True}, indent=2))
    else:
        print(result.token)
    if args.verbose:
        say(f"solved in {result.elapsed:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
