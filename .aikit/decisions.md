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

## Licensing migration (v0.1.0-al-1.0)

- New versions use the Aegean License 1.1 (AL-1.1); versions up to and including `v0.1.0-al-1.0` remain under the Aegean License 1.0 (AL-1.0).
- Rights holder: AegeanWorks; commercial use under ACL-1.0.
- Counsel review of the 1.1 texts remains pending.

## License notice cleanup (2026-10-26)

- The license-history notes and the old-license boundary tag were removed: the project is offered only under the Aegean License 1.1 (AL-1.1), with commercial use under ACL-1.0.
