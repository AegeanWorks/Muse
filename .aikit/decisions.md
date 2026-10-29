# Decisions

Why this project is built the way it is, oldest first. One entry per decision that changes a
contract, a dependency, a data format or the architecture; IDs are consecutive and never reused.

<!-- Entry format:
### ADR-NNN: <decision in one line>
- **Date**: YYYY-MM-DD
- **Status**: Accepted
- **Context**: <what forced the decision>
- **Decision**: <what was decided>
- **Consequences**: <what follows, including what it costs>
-->

### ADR-001: Providers and judges are protocol boundaries with registries
- **Date**: 2026-10-26
- **Status**: Accepted
- **Context**: Hosted music models and audio-capable judges change faster than the pipeline, and the regression suite must run offline without keys or cost.
- **Decision**: `MusicProvider` and `MusicJudge` are protocols; `providers/registry.py` and `judges/registry.py` resolve names; `mock` adapters implement both boundaries; the pipeline depends only on the protocols.
- **Consequences**: Adding a vendor is one adapter plus one registry entry, and tests stay free, fast and deterministic. The cost is manual request mapping per model, and model-specific knobs must travel through `MusicRequest.extra`.

### ADR-002: Every render ships with evidence, and acceptance is explicit
- **Date**: 2026-10-26
- **Status**: Accepted
- **Context**: A track is only useful to another project if the reason it was accepted can be inspected and re-checked later; automation also needs an exit code.
- **Decision**: `compose` writes the audio and `muse.json` atomically; the verdict carries the configured threshold; `--strict` exits `1` below it. A required judge failure keeps the audio and records `judge_error` before raising, while a failed render deletes its empty run folder.
- **Consequences**: Downstream projects can gate on `accepted` and retain the evidence beside the asset. The cost is disk usage per attempt and a metadata schema that must be versioned when its shape changes.

### ADR-003: Zero runtime dependencies, standard-library HTTP only
- **Date**: 2026-10-26
- **Status**: Accepted
- **Context**: The portfolio's other local tools install instantly and run on any Python 3.10+ machine; a vendor SDK would add transitive dependencies and pin the project to one provider.
- **Decision**: Use `urllib`, `json`, `wave` and `dataclasses` only. The retry, backoff, timeout, atomic download and inline-audio limit rules live in `muse/net.py` and the adapters.
- **Consequences**: No install step and no dependency drift; both providers share one tested HTTP policy. The cost is owning retry and schema handling that SDKs would otherwise supply.

### ADR-004: Rejected takes are retried with the judge's suggestions, and the best take wins
- **Date**: 2026-10-29
- **Status**: Accepted
- **Context**: The judge already returns concrete prompt suggestions, but the pipeline printed them and stopped; improving a rejected track meant a human rewriting the prompt and re-running the command.
- **Decision**: `--attempts N` (1-5, default 1) renders a take, judges it, and while the score is below the threshold, the verdict has suggestions, and takes remain, appends those suggestions to the prompt and renders again. Every take keeps its own artifact folder; the selected take is the highest score, ties going to the earlier take, and its `muse.json` (schema 2) records `attempt`, `selected_attempt` and the full `attempts` history. `--attempts` above 1 requires a listening judge; `--strict` judges the selected take.
- **Consequences**: One command can reach an acceptable score without a human loop, and every rejected take remains auditable. The cost is one provider prediction and one judge call per take, plus cosmetic folder suffixes; refinement is a bounded heuristic (suggestions are appended, not rewritten), so a judge that offers nothing actionable stops the loop early.

### ADR-005: Batch mode reads one validated manifest and renders tracks sequentially
- **Date**: 2026-10-29
- **Status**: Accepted
- **Context**: A project soundtrack is a set of themed tracks, but every track required its own CLI invocation, so automation repeated flags and could not report a set-level result.
- **Decision**: `muse batch <manifest>` reads a UTF-8 JSON object with a single `tracks` array (1-50 entries, at most 1 MB), validates every `prompt`, `theme`, `duration` and `name` before the first paid call, and runs the existing `compose` pipeline per track with the same `--attempts` setting. Tracks render sequentially; the batch stops on the first operational failure, requires a listening judge, and exposes `--strict` (exit 1 when any track is rejected) and `--json` (`tracks`, `total`, `accepted`). Each track keeps its normal artifact folder and no separate batch summary file is written.
- **Consequences**: One manifest produces a fully judged soundtrack with a single exit code, while interrupted runs leave every completed track inspectable. The cost is sequential wall-clock time, one prediction and judge call per take per track, and a deliberately narrow manifest schema (unknown keys and types are rejected rather than guessed).

### ADR-006: Batch progress is fingerprinted state, and resume reuses only verified accepted takes
- **Date**: 2026-10-29
- **Status**: Accepted
- **Context**: A batch stopped on the first provider or judge failure, and rerunning the manifest re-rendered and re-billed tracks that had already been accepted.
- **Decision**: Every batch writes `<out>/.muse-batch-<fingerprint16>.json` atomically after each track. The fingerprint hashes the validated prompt, theme, duration and name in order, so a changed manifest cannot reuse stale progress. `--resume` requires that state, refuses a different fingerprint, reuses an accepted entry only when its audio and `muse.json` still exist, and rerenders rejected, failed or missing-evidence tracks. `--keep-going` records a failure and continues; without it the failure is recorded and re-raised. Failed entries carry an error and exit `1`; `--json` adds `rejected`, `failed`, `reused` counts and a per-track `reused` flag.
- **Consequences**: Long soundtracks finish past one bad track and resume without paying twice for accepted work, while the state file remains disposable and never replaces per-track evidence. The cost is one small hidden JSON file per manifest fingerprint, a resume that is tied to the same `--out` and working directory for relative evidence paths, and the rule that changing any track field starts a fresh state.

### ADR-007: Public inputs are validated and artifact writes fail as clean errors
- **Date**: 2026-10-29
- **Status**: Accepted
- **Context**: A hardening audit found library callers could pass non-string text, boolean or NaN durations, and string output directories that failed later with AttributeError or TypeError. Malformed provider and state payloads could traceback, failed JSON serialization left temp files behind, Windows reserved device names could break folder creation, and downloads accepted non-http schemes, empty bodies and unbounded streams.
- **Decision**: `MusicRequest`, `Verdict` and `MuseConfig` validate types, finite bounds and acceptance values at construction, and coerce `output_dir` to `Path`. `slugify` suffixes Windows reserved names. `unique_directory` uses atomic `mkdir`, `write_json_atomic` cleans its temp file on failure, fsyncs the file and (on POSIX) the directory, and reports `OSError` as `MuseError`. Downloads accept only http(s), reject empty bodies, cap the stream at 128 MB, retry truncated responses and report folder failures. Gemini checks the file size before reading. Manifest and batch-state reads are bounded, and Replicate validates handles and poll responses and evaluates the final poll.
- **Consequences**: Invalid inputs now fail at the public boundary instead of surfacing later as tracebacks, and interrupted or failed writes leave the previous evidence intact. The cost is stricter library validation (float thresholds and boolean durations are rejected), a 128 MB download ceiling, and directory fsync skipped on Windows where the operation is unavailable.

### ADR-008: Batch dry-run validates a plan without spending or writing
- **Date**: 2026-10-29
- **Status**: Accepted
- **Context**: A 50-track manifest with up to five takes per track can cost hundreds of provider and judge calls, but there was no way to validate the manifest and inspect the plan before spending.
- **Decision**: `muse batch --dry-run` validates the manifest with the normal loader, then prints each track's name, prompt, theme and duration plus the provider, judge, output root and attempt count. It writes no artifacts or batch state and calls neither the provider nor the judge, so it also accepts `--judge none`. With `--json` it emits a `dry_run: true` payload with the same track list.
- **Consequences**: A costly plan can be reviewed and corrected before the first paid call, and CI can validate manifests without keys. The cost is a second rendering path for the batch summary and the rule that dry-run properties (provider/judge names) are reported but not resolved, so an unknown provider is caught only by a real run.

### ADR-009: The artifact catalog is a read-only evidence view
- **Date**: 2026-10-29
- **Status**: Accepted
- **Context**: Every run writes `muse.json` evidence, but the only way to find and compare finished tracks was to walk the output folders by hand; batch summaries only cover one run.
- **Decision**: `muse list` scans one output level for `muse.json`, accepts schema 1 and 2, validates the request, track and verdict fields, and reads each file through a 2 MB cap. Corrupt, oversized or unsupported metadata is reported as a warning and skipped; missing audio is marked but the entry remains visible. Results sort newest first by `created_at` then folder, support `--accepted-only`, `--limit` (default 20) and `--json`, and never call a provider or judge.
- **Consequences**: Finished evidence is reviewable in one read-only command and JSON consumers get stable fields without touching the filesystem. The cost is a second schema reader to keep in step with `muse.json`, and a listing that reports but cannot repair corrupt evidence.

### ADR-010: Replicate polling uses a monotonic wall-clock deadline
- **Date**: 2026-10-29
- **Status**: Accepted
- **Context**: `MUSE_POLL_TIMEOUT` was converted into a number of poll attempts, so slow HTTP responses could exceed the configured wait by minutes or hours, and the final poll was previously discarded.
- **Decision**: Track a deadline with an injectable monotonic clock. Before each sleep, compute the remaining budget, sleep at most that remainder, and fail once the budget is exhausted; always evaluate the last poll response before deciding. Polls use the smaller of the poll interval and the remaining budget.
- **Consequences**: `MUSE_POLL_TIMEOUT` now means actual wall-clock time including request latency, and tests can drive the clock deterministically. The cost is an injected clock parameter on the provider and no retry of a poll that starts after the deadline.

### ADR-011: A required judge is built before the first render
- **Date**: 2026-10-29
- **Status**: Accepted
- **Context**: `compose` built the judge after the provider had already rendered, so a missing `GEMINI_API_KEY` or an unknown judge name spent a prediction and left evidence before failing. `--allow-unjudged` also failed on judge construction errors instead of returning the unjudged take.
- **Decision**: When `require_judge` is true, build the judge before the first provider call and reuse it for every attempt. When `require_judge` is false, keep the lazy path but catch judge construction errors and return `(verdict=None, judge_error=...)` with the audio and metadata, so `--allow-unjudged` exits 0 as documented. An unknown judge under `--allow-unjudged` therefore also degrades to recorded evidence rather than a failed run.
- **Consequences**: Required-judge misconfiguration costs no provider calls, and unjudged runs preserve both audio and the reason judging was skipped. The cost is that `--allow-unjudged` can hide a judge-name typo from the exit code; `--strict` and the printed `judge_error` still expose it.

### ADR-012: One artifact can be inspected without reading JSON by hand
- **Date**: 2026-10-29
- **Status**: Accepted
- **Context**: `muse list` summarizes evidence, but understanding why a track was accepted or rejected still required opening `muse.json` and reconstructing the verdict, attempts and settings.
- **Decision**: `muse show <folder|muse.json|track-file>` resolves one artifact under `--out` or from a path, validates it through the catalog reader, and prints the prompt, theme, track, verdict, summary, strengths, issues, suggestions, judge error, attempt count and settings. `--json` prints the raw metadata object, and the command writes nothing.
- **Consequences**: A verdict is reviewable in one command and agents get the exact stored evidence with `--json`. The cost is a second human-facing renderer whose labels must stay aligned with the metadata schema.

### ADR-013: Batch builds the judge once before the track loop
- **Date**: 2026-10-29
- **Status**: Accepted
- **Context**: Batch passed no judge into `compose`, so every track rebuilt the same adapter; a missing key also surfaced only after the first track had been attempted and the state file written.
- **Decision**: Resolve the batch judge once after manifest validation and before loading or writing state, then pass that listener to every `compose` call. A missing key or unknown judge now fails before the first track, and a working judge is reused for the whole set.
- **Consequences**: One configuration error aborts a batch before any artifact or state write, and adapter construction happens once. The cost is that a judge whose configuration changes mid-run is not rebuilt; the manifest run is treated as one configuration snapshot.

### ADR-014: Dry-run can preview resume decisions from saved state
- **Date**: 2026-10-29
- **Status**: Accepted
- **Context**: `--resume` and `--dry-run` existed separately, so planning a resumed batch required either a real run or manually reading the hidden state file; a preview also had to prove it would not change that state.
- **Decision**: `muse batch --dry-run --resume` reads the fingerprinted state, checks accepted evidence with the same audio-and-metadata test as the real run, and marks every track `reuse` or `render` with a reason: new, previous rejection/failure, or missing evidence. The JSON plan includes `resume`, `action`, `reason`, `previous_status` and `previous_score`. The command writes nothing and calls neither provider nor judge; a missing state is refused exactly like a real resume.
- **Consequences**: The next paid run can be reviewed track by track, and the preview shares the real resume decision logic. The cost is that the preview is tied to the same `--out` and working directory as resume, and it reports decisions rather than revalidating the entire state file beyond the normal loader.

## Licensing migration (v0.1.0-al-1.0)

- New versions use the Aegean License 1.1 (AL-1.1); versions up to and including `v0.1.0-al-1.0` remain under the Aegean License 1.0 (AL-1.0).
- Rights holder: AegeanWorks; commercial use under ACL-1.0.
- Counsel review of the 1.1 texts remains pending.

## License notice cleanup (2026-10-26)

- The license-history notes and the old-license boundary tag were removed: the project is offered only under the Aegean License 1.1 (AL-1.1), with commercial use under ACL-1.0.
