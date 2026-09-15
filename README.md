<a href="https://peak.fo/?utm_source=github&utm_medium=readme&utm_campaign=packages&utm_content=cf-turnstile-token">
  <img src="./assets/peak-banner.png" alt="Peak - solve Cloudflare Turnstile & the 5s challenge in ~1s" width="100%">
</a>

# cf-turnstile-token

> Cloudflare Turnstile tokens from the command line - no browser, no
> maintenance, no guesswork.

Turnstile Token CLI reads the sitekey from any page (or takes it directly),
submits the solve task to the Peak API, and prints a valid
`cf-turnstile-response` token ready to inject into a request, a form, or an
automated flow. One Python file, standard library only, designed to run on
headless servers and CI runners.

## Why teams stop building their own solver

If you are currently maintaining a free or self-hosted solution - or you keep
patching around the widget yourself - you already know the rhythm. It works,
Cloudflare ships an update, it breaks, and your weekend disappears into
debugging something that is not your product.

| | DIY / free script | This CLI + Peak API |
|---|---|---|
| Time to first token | hours to days | about a second per token |
| Maintenance | yours, forever | handled server-side |
| Cloudflare widget updates | break your build | adapted for you |
| Browser required | often | never |
| Result per call | logs you parse | structured token or JSON |
| Cost | your time | from **$0.8 / 1,000** successful solves |

Free is only free until it costs you a weekend. A maintained solve API removes
the moving parts: no browser fleet, no per-site hacks, no guessing whether the
last update still works. You send the sitekey and the target URL, you get a
token back.

## Features

- **Automatic sitekey discovery** - point it at a page and it finds the
  `data-sitekey` for you (`--list-sitekeys` prints them all).
- **Zero browser dependency** - a single Python file on the standard library;
  works the same on a headless CI runner as it does locally.
- **Batch mode** - solve a file of URLs in one call (`--batch`).
- **Retries with backoff** - transient failures retry automatically.
- **Structured output** - print the raw token or a JSON object for pipelines.
- **Proxy-aware** - pass a proxy so the solve comes from the same IP as your
  crawl or session.
- **Action / cdata support** - matches Turnstile configurations that require
  them.

## Install

No third-party runtime dependencies. Copy `cf_turnstile_token.py` anywhere, or
install the package and use the console script:

```console
$ pip install .
$ cf-turnstile-token --version
cf-turnstile-token 1.0.0
```

## Quick start

```console
$ export PEAK_API_KEY=pk_your_api_key
$ cf-turnstile-token --page https://example.com/protected --url https://example.com/
sitekey: 0x4AAAAAAAxxxx
0.AgAAABBqzz...
```

With an explicit sitekey and a proxy:

```console
$ cf-turnstile-token --sitekey 0x4AAAAAAAxxxx --url https://example.com/ \
    --proxy http://user:pass@1.2.3.4:8080
0.AgAAABBqzz...
```

JSON output for pipelines:

```console
$ cf-turnstile-token --page https://example.com/ --url https://example.com/ --output json
{
  "token": "0.AgAAABBqzz...",
  "success": true
}
```

## CLI reference

| Option | Description |
|---|---|
| `--sitekey KEY` | Turnstile sitekey (`0x...`), if you already know it |
| `--page URL` | Page to auto-extract the sitekey from |
| `--url URL` | Target page URL - must end with `/` |
| `--proxy URL` | `http://user:pass@ip:port`, to match your session IP |
| `--action V` / `--cdata V` | Optional Turnstile action / cdata values |
| `--output text\|json` | Raw token or structured JSON (default `text`) |
| `--batch FILE` | Solve one target URL per line; prints a JSON result list |
| `--list-sitekeys` | With `--page`: print every sitekey found and exit |
| `--api-key KEY` | Peak API key (default: `PEAK_API_KEY` env var) |
| `--retries N` / `--timeout S` | Tuning for slow or flaky links |
| `--quiet` / `--verbose` | Progress output off / detailed |

## Python API

```python
from cf_turnstile_token import extract_sitekey, read_page, solve, PeakError

html = read_page("https://example.com/protected")
sitekey = extract_sitekey(html)

try:
    result = solve("pk_...", sitekey, "https://example.com/")
    print(result.token)          # -> "0.AgAAABBqzz..."
except PeakError as exc:
    print(f"solve failed: {exc}")
```

Batch solving:

```python
from cf_turnstile_token import solve_many

results = solve_many("pk_...", [
    {"sitekey": "0xAAA", "url": "https://example.com/"},
    {"sitekey": "0xBBB", "url": "https://example.org/"},
])
```

## Recipes

CI / shell - pipe the token into any request:

```bash
TOKEN=$(cf-turnstile-token --page https://example.com/ --url https://example.com/)
curl -X POST https://example.com/submit \
  -H "cf-turnstile-response: $TOKEN" \
  -d "payload=..."
```

Several pages at once:

```bash
cf-turnstile-token --batch targets.txt --output json > tokens.json
```

## How it works

1. **Sitekey discovery** - with `--page`, the tool fetches the page and extracts
   the Turnstile `data-sitekey` (most pages have exactly one).
2. **Solve request** - it POSTs a `turnstiletask` to the Peak API
   (`https://api.peak.fo/solve`) with the sitekey, target URL, and any optional
   proxy/action/cdata values.
3. **Token returned** - the response carries `data.token`; submit it as the
   `cf-turnstile-response` field (or the equivalent parameter your target
   expects).

The API contract is documented at
[peak.fo/docs/turnstile](https://peak.fo/docs/turnstile?utm_source=github&utm_medium=readme&utm_campaign=packages&utm_content=cf-turnstile-token).

## FAQ

**Does it run headless / without a browser?**

Yes. The whole tool is one Python file on the standard library - no browser, no
webdriver, no Node. It behaves the same on a headless CI runner as it does
locally.

**Why not just keep using a free script I found?**

You can - until it breaks. Free scripts are updated when someone has time, so
every Cloudflare change becomes your problem: failed runs, stale tokens, and
hours of debugging. This CLI stays thin on purpose and lets the maintained API
absorb that work, so the tool keeps returning tokens while you keep shipping.

**How do I use a proxy?**

Pass `--proxy http://user:pass@ip:port`. Use the same egress IP as the session
that will submit the token - Turnstile tokens are bound to the IP, URL and
user-agent that solved them.

**How long is a token valid?**

Tokens are short-lived. Request one right before you submit the form, and do
not cache them across runs.

**Why was my token rejected?**

Almost always a mismatch: the solve came from a different proxy/IP than the
submission, a different user-agent, or a different URL. Solve and submit with
the same values.

## Powered by Peak

This package uses [Peak](https://peak.fo/?utm_source=github&utm_medium=readme&utm_campaign=packages&utm_content=cf-turnstile-token) to solve Turnstile.

- ✅ **1,000 free solves to start - no card.** [Grab 1,000 free solves](https://peak.fo/?utm_source=github&utm_medium=readme&utm_campaign=packages&utm_content=cf-turnstile-token) and pay only for successful solves.
- From **$0.8 / 1,000** successful solves.
- Solve Cloudflare Turnstile & the 5s challenge in about a second.

[Get your free API key](https://peak.fo/?utm_source=github&utm_medium=readme&utm_campaign=packages&utm_content=cf-turnstile-token) • [Docs](https://peak.fo/docs/turnstile?utm_source=github&utm_medium=readme&utm_campaign=packages&utm_content=cf-turnstile-token) • [Pricing](https://peak.fo/pricing?utm_source=github&utm_medium=readme&utm_campaign=packages&utm_content=cf-turnstile-token)

---

<p align="center">
  <b>You're looking at the work.</b><br>
  <sub>Want the same for your service, product or repository — including a spot in the <b>top 1–5 GitHub search results</b> for your keywords? <b>Message me on Telegram</b> and I'll share the details.</sub>
</p>

<p align="center">
  🔥 Targeted keywords&nbsp; •&nbsp; 🌍 Global reach&nbsp; •&nbsp; 🔝 Top search visibility<br>
  <sub>Others are already getting more responses and more sales from this.</sub>
</p>

<p align="center">
  <a href="https://t.me/AlpinTamhas928"><b>✉️ Telegram — @AlpinTamhas928</b></a><br>
  <sub>Reach out anytime · friendly rates · small projects welcome</sub>
</p>


## License

MIT
