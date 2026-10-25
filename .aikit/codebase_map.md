# Codebase Map & Symbol Catalog 🗺️

> **AUTO-GENERATED & VERIFIED BY `scripts/update_knowledge_base.py`**
> This document provides an automated, up-to-date registry of all modules, classes, and exported functions across this repository.

---

## 📊 Codebase Metrics
- **Total Python Modules**: `26`
- **Total Classes**: `40`
- **Total Top-Level Functions**: `34`
- **Total Class Methods**: `125`
- **Total Source Lines**: `2061`

---

## 📦 Modules & Exported Symbols

### [`muse/__init__.py`](muse/__init__.py)
> *Muse: prompt-driven music with an automated listener.*

**Size**: `24` lines (`564` bytes)

---

### [`muse/__main__.py`](muse/__main__.py)
> *Entry point for ``python -m muse``.*

**Size**: `7` lines (`127` bytes)

---

### [`muse/artifacts.py`](muse/artifacts.py)
> *Artifact directories and crash-safe JSON metadata.*

**Size**: `34` lines (`981` bytes)

**Functions:**
- `def unique_directory(parent, label)`
- `def write_json_atomic(path, payload)`

---

### [`muse/audio.py`](muse/audio.py)
> *Small audio helpers that need no third-party packages.*

**Size**: `51` lines (`1526` bytes)

**Functions:**
- `def slugify(text, fallback)`
- `def mime_type(path)`
- `def wav_duration(path)`
- `def write_tone(path, seconds, sample_rate)` - *Write a quiet sine chord so offline mocks produce a valid WAV.*

---

### [`muse/cli.py`](muse/cli.py)
> *Command line interface: generate, judge, inspect providers.*

**Size**: `242` lines (`9215` bytes)

**Functions:**
- `def main(argv, *, config, provider, judge)`
- `def build_parser()`
- `def _common(parser)`
- `def _settings(args, config)`
- `def _generate(args, settings, provider, judge)`
- `def _judge(args, settings, judge)`
- `def _providers(args)`
- `def _result_payload(result)`
- `def _verdict_payload(verdict, path)`
- `def _verdict_dict(verdict)`
- `def _print_result(result)`
- `def _print_verdict(verdict)`

---

### [`muse/config.py`](muse/config.py)
> *Configuration resolved from explicit values, environment variables and defaults.*

**Size**: `112` lines (`4421` bytes)

**Classes:**
- `class MuseConfig`
  - Method `.__post_init__()`
  - Method `.from_env(env)`
  - Method `.with_overrides(**changes)`
  - Method `.replicate_token()`
  - Method `.gemini_key()`

**Functions:**
- `def _int(raw, default, name)`
- `def _float(raw, default, name)`

---

### [`muse/errors.py`](muse/errors.py)
> *User-facing failures with what, why and how to fix them.*

**Size**: `26` lines (`528` bytes)

**Classes:**
- `class MuseError`
  - Method `.__init__(what, why, fix)`
  - Method `.render()`
- `class ConfigurationError`
- `class GenerationError`
- `class JudgeError`

---

### [`muse/judges/base.py`](muse/judges/base.py)
> *The listening boundary every judge implements.*

**Size**: `16` lines (`393` bytes)

**Classes:**
- `class MusicJudge`
  - Method `.judge(track, request)` - *Listen to the track and score how well it serves the request's theme.*

---

### [`muse/judges/gemini.py`](muse/judges/gemini.py)
> *Gemini audio judge: listens to the rendered track and scores theme fit.*

**Size**: `154` lines (`6281` bytes)

**Classes:**
- `class GeminiJudge`
  - Method `.__init__(config, http)`
  - Method `.judge(track, request)`
  - Method `._payload(track, request)`
  - Method `._parse(response)`

**Functions:**
- `def _validate(data)`
- `def _strings(value)`

---

### [`muse/judges/mock.py`](muse/judges/mock.py)
> *Deterministic offline judge used by tests and demos.*

**Size**: `50` lines (`1826` bytes)

**Classes:**
- `class MockJudge`
  - Method `.__init__(config)`
  - Method `.judge(track, request)`

**Functions:**
- `def _words(text)`

---

### [`muse/judges/registry.py`](muse/judges/registry.py)
> *Name-to-judge lookup so callers never import adapters directly.*

**Size**: `34` lines (`1047` bytes)

**Functions:**
- `def build_judge(name, config)`
- `def judges()`

---

### [`muse/net.py`](muse/net.py)
> *Minimal JSON and download HTTP client with retry and timeouts.*

**Size**: `146` lines (`5654` bytes)

**Classes:**
- `class HttpResponse`
  - Method `.json()`
- `class HttpClient`
  - Method `.__init__(timeout, retries, backoff, sleep, opener)`
  - Method `.json(method, url, payload, headers)`
  - Method `.download(url, destination, headers)`
  - Method `._stream(request, path)`
  - Method `._send(method, url, payload, headers, retries)`
  - Method `._once(method, url, body, headers)`

**Functions:**
- `def _excerpt(body, limit)`

---

### [`muse/pipeline.py`](muse/pipeline.py)
> *Orchestration: render a prompt, listen to it, and persist the evidence.*

**Size**: `125` lines (`3930` bytes)

**Functions:**
- `def compose(request, config, provider, judge, require_judge)`
- `def judge_track(track, request, config, judge)`
- `def _listen(track, request, settings, judge, require_judge)`
- `def _metadata(request, track, verdict, judge_error, settings)`

---

### [`muse/providers/base.py`](muse/providers/base.py)
> *The generation boundary every music provider implements.*

**Size**: `17` lines (`409` bytes)

**Classes:**
- `class MusicProvider`
  - Method `.generate(request, destination)` - *Render the request into a file inside destination.*

---

### [`muse/providers/mock.py`](muse/providers/mock.py)
> *Offline provider used by tests and demos.*

**Size**: `31` lines (`829` bytes)

**Classes:**
- `class MockMusicProvider`
  - Method `.__init__(config)`
  - Method `.generate(request, destination)`

---

### [`muse/providers/registry.py`](muse/providers/registry.py)
> *Name-to-provider lookup so callers never import adapters directly.*

**Size**: `33` lines (`1009` bytes)

**Functions:**
- `def build_provider(name, config)`
- `def providers()`

---

### [`muse/providers/replicate.py`](muse/providers/replicate.py)
> *Music generation through Replicate-hosted models.*

**Size**: `115` lines (`4464` bytes)

**Classes:**
- `class ReplicateMusicProvider`
  - Method `.__init__(config, http, sleep, poll_interval)`
  - Method `.generate(request, destination)`
  - Method `._create(request)`
  - Method `._wait(created)`
  - Method `._output_url(final)`

---

### [`muse/types.py`](muse/types.py)
> *Public data types shared by providers, judges and the pipeline.*

**Size**: `83` lines (`2026` bytes)

**Classes:**
- `class MusicRequest` - *A prompt plus the theme it must serve.*
  - Method `.__post_init__()`
  - Property `.intent` - *The theme when given, else the prompt.*
  - Property `.label`
- `class Track`
- `class Verdict`
  - Property `.accepted`
- `class CompositionResult`
  - Property `.accepted`

---

### [`tests/__init__.py`](tests/__init__.py)
> *Regression shield for Muse.*

**Size**: `1` lines (`34` bytes)

---

### [`tests/test_audio.py`](tests/test_audio.py)
**Size**: `55` lines (`2199` bytes)

**Classes:**
- `class SlugTests`
  - Method `.test_slugifies_prompt()`
  - Method `.test_falls_back_when_nothing_remains()`
- `class MimeTests`
  - Method `.test_known_and_unknown_suffixes()`
- `class ToneTests`
  - Method `.test_writes_a_readable_wav()`
  - Method `.test_duration_of_non_wav_is_none()`
- `class ArtifactTests`
  - Method `.test_unique_directories_get_suffixes()`
  - Method `.test_json_write_leaves_no_temp_file()`

---

### [`tests/test_cli.py`](tests/test_cli.py)
**Size**: `122` lines (`4902` bytes)

**Classes:**
- `class CliTests`
  - Method `.setUp()`
  - Method `.run_cli(argv)`
  - Method `.test_generate_json()`
  - Method `.test_strict_rejects_low_score()`
  - Method `.test_judge_existing_file()`
  - Method `.test_judge_missing_file_exits_one()`
  - Method `.test_judge_none_is_explained()`
  - Method `.test_providers_json()`
  - Method `.test_version_exits_zero()`
  - Method `.test_empty_prompt_is_misuse_without_traceback()`
  - Method `.test_duration_beyond_model_limit_is_misuse()`
  - Method `.test_min_score_outside_percent_is_reported()`
  - Method `.test_judge_reports_strengths()`
  - Method `.test_unknown_flag_is_misuse()`
  - Method `.test_unknown_provider_exits_one()`

---

### [`tests/test_judges.py`](tests/test_judges.py)
**Size**: `123` lines (`5134` bytes)

**Classes:**
- `class FakeHttp`
  - Method `.__init__(response)`
  - Method `.json(method, url, payload, headers)`
- `class GeminiTests`
  - Method `.setUp()`
  - Method `.test_sends_audio_and_returns_verdict()`
  - Method `.test_invalid_score_is_rejected()`
  - Method `.test_unknown_verdict_is_rejected()`
  - Method `.test_missing_candidate_is_rejected()`
  - Method `.test_oversized_audio_is_rejected_before_upload()`
  - Method `.test_empty_verdict_text_is_rejected()`
- `class MockJudgeTests`
  - Method `.setUp()`
  - Method `.track()`
  - Method `.test_shared_terms_fit()`
  - Method `.test_disjoint_terms_miss()`
  - Method `.test_missing_theme_is_partial()`
- `class JudgeRegistryTests`
  - Method `.test_unknown_judge_is_explained()`
  - Method `.test_mock_judge_is_pickable()`

**Functions:**
- `def reply(**changes)`

---

### [`tests/test_net.py`](tests/test_net.py)
**Size**: `115` lines (`4482` bytes)

**Classes:**
- `class FlakyClient`
  - Method `.__init__(responses)`
  - Method `._once(method, url, body, headers)`
- `class HttpClientTests`
  - Method `.test_retries_retryable_status()`
  - Method `.test_does_not_retry_client_error()`
  - Method `.test_retries_are_exhausted()`
  - Method `.test_non_json_body_is_explained()`
- `class FakeResponse`
  - Method `.__init__(chunks)`
  - Method `.__enter__()`
  - Method `.__exit__(*exc_info)`
  - Method `.read(size)`
- `class ScriptedOpener`
  - Method `.__init__(actions)`
  - Method `.__call__(request, timeout)`
- `class DownloadTests`
  - Method `.test_failed_download_leaves_no_partial_file()`
  - Method `.test_download_retries_transport_failure()`
  - Method `.test_download_does_not_retry_http_404()`

---

### [`tests/test_pipeline.py`](tests/test_pipeline.py)
**Size**: `117` lines (`5043` bytes)

**Classes:**
- `class FailingJudge`
  - Method `.judge(track, request)`
- `class FailingProvider`
  - Method `.generate(request, destination)`
- `class PipelineTests`
  - Method `.setUp()`
  - Method `.test_compose_writes_audio_verdict_and_metadata()`
  - Method `.test_second_composition_gets_a_unique_folder()`
  - Method `.test_judge_none_skips_listening()`
  - Method `.test_required_judge_failure_raises_but_keeps_evidence()`
  - Method `.test_optional_judge_failure_keeps_audio()`
  - Method `.test_tokens_never_reach_metadata()`
  - Method `.test_failed_generation_removes_empty_run_folder()`
  - Method `.test_judge_track_uses_injected_judge()`

---

### [`tests/test_providers.py`](tests/test_providers.py)
**Size**: `135` lines (`5780` bytes)

**Classes:**
- `class FakeHttp`
  - Method `.__init__(responses)`
  - Method `.json(method, url, payload, headers)`
  - Method `.download(url, destination, headers)`
- `class ReplicateTests`
  - Method `.setUp()`
  - Method `.test_official_model_flow()`
  - Method `.test_pinned_version_uses_predictions_endpoint()`
  - Method `.test_failed_prediction_is_reported()`
  - Method `.test_timeout_is_reported()`
  - Method `.test_empty_output_is_reported()`
  - Method `.test_missing_handle_is_reported()`
- `class RegistryTests`
  - Method `.test_mock_provider_is_pickable()`
  - Method `.test_unknown_provider_is_explained()`
  - Method `.test_mock_provider_writes_a_file()`

**Functions:**
- `def config(**changes)`

---

### [`tests/test_types.py`](tests/test_types.py)
**Size**: `93` lines (`3630` bytes)

**Classes:**
- `class MusicRequestTests`
  - Method `.test_theme_defaults_to_prompt_intent()`
  - Method `.test_theme_wins_as_intent()`
  - Method `.test_empty_prompt_is_rejected()`
  - Method `.test_duration_bounds()`
  - Method `.test_label_prefers_name_then_theme()`
- `class VerdictTests`
  - Method `.test_accepts_at_threshold()`
  - Method `.test_rejects_below_threshold()`
- `class ConfigTests`
  - Method `.test_defaults()`
  - Method `.test_environment_overrides()`
  - Method `.test_invalid_number_is_a_configuration_error()`
  - Method `.test_threshold_outside_percent_is_rejected()`
  - Method `.test_non_positive_timeouts_are_rejected()`
  - Method `.test_missing_tokens_are_explained()`
  - Method `.test_tokens_are_not_in_repr()`

---
