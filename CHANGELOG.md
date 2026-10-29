# Changelog

All notable changes to Muse are recorded here. Versions follow the project's
`major.minor.patch` numbering; the package and `muse --version` must agree.

## [Unreleased]

### Added

- This changelog covering the 0.1.0 through 0.10.0 release line.

## [0.14.2] - 2026-10-29

### Fixed

- `muse rejudge` resolves duplicate artifact paths once, avoiding duplicate
  judge calls and history entries.

## [0.14.1] - 2026-10-29

### Fixed

- Rejudged evidence records the judge and model reported by the new verdict,
  rather than the configured names, so aliased/injected judges are attributed
  correctly.

## [0.14.0] - 2026-10-29

### Added

- `muse rejudge ARTIFACT...` re-scores existing audio without a provider and
  writes schema-3 evidence with a history array of prior verdicts and settings.

## [0.13.3] - 2026-10-29

### Added

- `muse show` lists every take in multi-attempt evidence with score, verdict,
  audio path and a selected marker.

## [0.13.2] - 2026-10-29

### Fixed

- `muse doctor --json` reports an invalid environment as a configuration check
  instead of failing before it can emit JSON.
- Missing explicit `muse show` paths point at the intended `muse.json` instead
  of doubling the filename.

## [0.13.1] - 2026-10-29

### Fixed

- Mock judging matches Unicode terms instead of dropping non-ASCII words.
- Turkish and accented text is transliterated into readable artifact slugs.
- `muse show` bare names resolve under `--out` before the working directory.

## [0.13.0] - 2026-10-29

### Added

- `muse generate --dry-run` validates a single request and prints its resolved
  provider, judge, attempts and output plan without any provider or judge call.

## [0.12.1] - 2026-10-29

### Fixed

- `muse list` now reports `total` matches and `shown` rows separately, so
  `--limit` no longer hides the true result count.

## [0.12.0] - 2026-10-29

### Added

- `muse doctor` checks Python, output writability, provider/judge names and
  required keys without network calls or writes; supports JSON and overrides.

## [0.11.0] - 2026-10-29

### Added

- `muse batch --resume --force NAME` rerenders selected accepted tracks while
  reusing the rest; unknown names and use without `--resume` are rejected.

## [0.10.0] - 2026-10-29

### Added

- `muse list --match TEXT` for case-insensitive name, prompt and theme filtering.
- `muse list --sort date|score|name`; filtering and sorting happen before `--limit`.

## [0.9.1] - 2026-10-29

### Fixed

- A fully accepted batch resume no longer requires a judge or key.
- Catalog rejects both path separators in `track.file` on every platform.
- Multi-take history read/parse failures raise a clean `MuseError`.

## [0.9.0] - 2026-10-29

### Added

- `muse batch --dry-run --resume` previews `reuse`/`render` decisions and reasons
  without writing state or calling a provider.

## [0.8.0] - 2026-10-29

### Added

- `muse show` prints one artifact's verdict, suggestions, attempts and settings;
  `--json` prints the raw evidence.
- Batch builds one judge before the track loop.

## [0.7.1] - 2026-10-29

### Fixed

- Required judges are built before the first render, so a missing key costs no
  prediction.
- `--allow-unjudged` keeps audio and exits 0 when the judge cannot be built.

## [0.7.0] - 2026-10-29

### Added

- `muse list` read-only evidence catalog with accepted filtering, limits and JSON.
- Replicate polling uses a monotonic wall-clock deadline.

## [0.6.0] - 2026-10-29

### Added

- `muse batch --dry-run` validates a manifest and prints the plan without spending.

### Fixed

- Filesystem failures become clean exits; environment paths are trimmed and expanded.
- `Verdict` sequences are normalized and malformed Gemini replies are rejected.

## [0.5.1] - 2026-10-29

### Fixed

- Strict input validation for requests, verdicts and configuration.
- Durable, atomic artifact writes; bounded manifest, state and download reads.
- HTTP downloads accept only http(s), reject empty/truncated bodies and cap size.
- Windows reserved folder names are avoided.

## [0.5.0] - 2026-10-29

### Added

- Fingerprinted batch state, `--resume`, `--keep-going` and `rejected`/`failed`/`reused`
  summary counts.

## [0.4.0] - 2026-10-29

### Added

- `muse batch` renders and judges a JSON manifest with `--strict` and `--json`.

## [0.3.0] - 2026-10-29

### Added

- `--attempts N` retries rejected takes with the judge's suggestions and keeps the
  best attempt; `muse.json` schema 2 records attempt history.

## [0.2.0] - 2026-10-26

### Changed

- Licensing moved to the Aegean License 1.1 (AL-1.1), with commercial use under
  ACL-1.0 and reviewed brand assets.

## [0.1.0] - 2026-10-26

### Added

- Initial Muse MVP: provider/judge protocols, Replicate and Gemini adapters,
  crash-safe artifacts, CLI/library API and an offline test suite.
