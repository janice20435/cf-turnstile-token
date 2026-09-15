# Changelog

All notable changes to this project are documented here.
The format follows Keep a Changelog; versioning follows SemVer.

## 1.0.0

First public release.

- `cf-turnstile-token` CLI: `--sitekey` / `--page` / `--url`, text or JSON output.
- Automatic Turnstile sitekey discovery on a page (`extract_sitekey`,
  `extract_sitekeys`, `--list-sitekeys`).
- Peak API solve client with retries and backoff (`solve`).
- Batch solving for a list of URLs (`solve_many`, `--batch FILE`).
- Zero third-party runtime dependencies, Python 3.8+.
- Examples: batch solving, stdlib submission, sitekey discovery.
- Unit tests for parsing, payloads, retries and the CLI surface.
