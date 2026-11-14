# Muse — agent contract

Muse renders prompt-driven music, has a judge listen to it, and records why each track was
accepted. This file is the short contract for an AI agent driving the tool; the README is the
human tour. If they disagree, the CLI and tests are right and this file is a bug.

## Run it

- Python 3.10+, standard library only. No install step: run `python -m muse ...` from the
  repository root (or use the installed `muse` entry point; both are the same CLI).
- Offline, free and deterministic: `--provider mock --judge mock`. Every example below works with
  those adapters and needs no keys.
- Real generation reads `REPLICATE_API_TOKEN` and `GEMINI_API_KEY` from the environment. Never
  print, log or commit either value.
- Settings also come from `MUSE_OUTPUT_DIR`, `MUSE_PROVIDER`, `MUSE_JUDGE`, `MUSE_MUSIC_MODEL`,
  `MUSE_JUDGE_MODEL`, `MUSE_MIN_SCORE`, `MUSE_HTTP_TIMEOUT` and `MUSE_POLL_TIMEOUT`; a CLI flag
  wins over the environment.

## Output contract

- Every data command accepts `--json` and prints exactly one JSON object on stdout. Parse stdout;
  never scrape the human report.
- A command that fails before it can produce a result prints nothing on stdout; the diagnostic
  goes to stderr as `Error: ...` with `Why:` and `Fix:` lines. A command that finished prints its
  one JSON object and reports the problem through the exit code instead: `doctor` with a failing
  check, a `--strict` rejection from `generate`, `judge`, `rejudge` or `batch`, and a
  `--keep-going` batch with a failed track all print JSON and exit `1`. Read both stdout and the
  exit code.
- Exit codes: `0` success; `1` operational failure, a `--strict` rejection, or a failed `doctor`;
  `2` argument misuse or an invalid request value. A non-strict generation whose score is below
  the threshold still exits `0` with `"accepted": false`.
- A required judge that fails keeps the audio and metadata when `--allow-unjudged` is set, records
  `judge_error`, and exits `0`; without that flag the same failure exits `1`.

## Commands

| Command | Purpose | JSON fields you can rely on |
|---|---|---|
| `generate PROMPT --theme T [--duration S] [--json]` | Render and judge one track | `audio`, `metadata`, `provider`, `model`, `duration_seconds`, `verdict`, `accepted`, `judge_error`, `attempts` |
| `generate ... --dry-run --json` | Validate and plan; no provider or judge call | `dry_run`, `request`, `attempts`, `provider`, `music_model`, `judge`, `judge_model`, `min_score`, `output` |
| `batch MANIFEST [--json]` | Render a JSON manifest of tracks | `tracks`, `total`, `accepted`, `rejected`, `failed`, `reused` |
| `batch MANIFEST --dry-run --json` | Plan a batch without spending | `dry_run`, `resume`, `tracks[]` (`name`, `action`, `reason`), `total`, `provider`, `judge`, `output` |
| `judge AUDIO --theme T [--json]` | Score an existing file | `audio`, `verdict`, `accepted` |
| `list [--accepted-only] [--json]` | Read the artifact catalog | `artifacts[]`, `total`, `shown`, `output`, `match`, `sort` |
| `show ARTIFACT [--json]` | Print one artifact's raw evidence | the `muse.json` object (`schema` 1-3: request, track, verdict, attempts, history) |
| `rejudge ARTIFACT... [--json]` | Re-score without rendering | `artifacts[]` (`old_score`, `score`, `verdict`, `accepted`, `history`), `total`, `accepted` |
| `analyze ARTIFACT... --requirements FILE [--json]` | Check audio against a consuming project's limits | `requirements` (`path`, `limits`), `artifacts[]` (`ok`, `checks[]`, `failed[]`, `skipped[]`, `profile`, `evidence`), `total`, `passed`, `failed` |
| `doctor [--json]` | Check the local setup; read-only | `ok`, `checks[]` (`name`, `ok`, `detail`) |
| `providers [--json]` | Names wired in | `providers`, `judges` |

`verdict` objects carry `score` (0-100), `verdict`, `summary`, `strengths`, `issues`,
`suggestions`, `judge`, `model` and `threshold`.

## Requirement analysis

`muse analyze` answers the consuming project's question directly: does this track meet the stated
limits? The requirements file is one JSON object; every key is optional, at least one is required,
and unknown keys are rejected:

```json
{"min_duration": 28, "max_duration": 32, "min_sample_rate": 22050,
 "channels": [1, 2], "sample_width_bits": [16], "max_peak_dbfs": -1.0,
 "min_rms_dbfs": -30.0, "max_size_mb": 25, "require_accepted": true,
 "min_score": 60}
```

- Technical checks read the WAV header and PCM samples: duration, sample rate, channels, bit
  depth, peak and RMS loudness in dBFS, clipping percent and file size. Non-WAV audio is not
  decoded; its technical checks are `skipped`, not failed, and the reason is in `detail`.
- `presets/keystone-audio.json` (`channels: [1]`, `sample_width_bits: [16]`) states Keystone's
  `read_wav` contract; a track that passes it loads through `keystone.audio.read_wav` unchanged.
- Judge checks (`require_accepted`, `min_score`) read `muse.json` evidence from the artifact
  folder; an audio file outside an artifact folder has none, so those checks are `skipped` with a
  hint to run `muse judge`.
- One failed check makes the artifact `ok: false` and the command exits `1`; skips never fail.
  A missing artifact or missing audio exits `1`; an invalid requirements file exits `2`. Like
  `doctor`, a finished analysis prints its JSON object before exiting `1`.
- `require_accepted` accepts only `true`; omit it to skip the acceptance check. Naming an audio
  file analyzes that file, even when a sibling `muse.json` describes a different track.

## Cost and safety rules

- A paid call is one provider render per take; `--attempts N` (1-5) multiplies renders for that
  track, and `batch` multiplies by tracks. `judge` and `rejudge` call only the judge.
- Plan first: `generate --dry-run --json` or `batch MANIFEST --dry-run --json` validates without
  calling anything. Validate a manifest at any time with `--judge none` and `--dry-run`.
- `--strict` turns a rejected take into exit `1`; use it in automation, not while exploring.
- Evidence lives in `<out>/<slug>/muse.json` beside `track.wav`; `--out` (or `MUSE_OUTPUT_DIR`)
  chooses the root. `output/` is not committed; read it with `list`/`show`, do not edit it by hand.
- `batch` writes `<out>/.muse-batch-<fingerprint>.json` after each track; `--resume` reuses only
  accepted takes whose audio and evidence still exist, and `--keep-going` records a failed track
  instead of stopping the run.
- Jobs are sequential and bounded: durations up to 190 s, attempts up to 5, manifests up to 50
  tracks and 1 MB. Do not retry a failed paid call in a tight loop; inspect the stderr `Why:`
  first.

## Verifying a change

```bash
python -m unittest discover -s tests -t .
python -m muse doctor --provider mock --judge mock --json
```

Both must pass before a commit. `python -m muse generate "cave drones" --theme "cave level"
--provider mock --judge mock` is the fast end-to-end smoke test; it writes into `output/` and
exits `0` with `"accepted": true`.
