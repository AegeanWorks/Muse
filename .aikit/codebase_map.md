# Codebase Map & Symbol Catalog 🗺️

> **AUTO-GENERATED & VERIFIED BY `scripts/update_knowledge_base.py`**
> This document provides an automated, up-to-date registry of all modules, classes, and exported functions across this repository.

---

## 📊 Codebase Metrics
- **Total Python Modules**: `33`
- **Total Classes**: `60`
- **Total Top-Level Functions**: `80`
- **Total Class Methods**: `279`
- **Total Source Lines**: `5312`

---

## 📦 Modules & Exported Symbols

### [`muse/__init__.py`](muse/__init__.py)
> *Muse: prompt-driven music with an automated listener.*

**Size**: `25` lines (`589` bytes)

---

### [`muse/__main__.py`](muse/__main__.py)
> *Entry point for ``python -m muse``.*

**Size**: `7` lines (`127` bytes)

---

### [`muse/artifacts.py`](muse/artifacts.py)
> *Artifact directories and crash-safe JSON metadata.*

**Size**: `88` lines (`2769` bytes)

**Functions:**
- `def unique_directory(parent, label)`
- `def write_json_atomic(path, payload)`
- `def _fsync_directory(path)`

---

### [`muse/audio.py`](muse/audio.py)
> *Small audio helpers that need no third-party packages.*

**Size**: `71` lines (`2150` bytes)

**Functions:**
- `def slugify(text, fallback)`
- `def mime_type(path)`
- `def wav_duration(path)`
- `def write_tone(path, seconds, sample_rate)` - *Write a quiet sine chord so offline mocks produce a valid WAV.*

---

### [`muse/batch.py`](muse/batch.py)
> *Batch manifest parsing: one JSON file, many themed tracks.*

**Size**: `142` lines (`5379` bytes)

**Functions:**
- `def load_manifest(path)` - *Read a JSON manifest and return one validated request per track.*
- `def _request(track, index)`
- `def _text(track, key, index)`

---

### [`muse/batch_state.py`](muse/batch_state.py)
> *Crash-safe progress state for resumable batch runs.*

**Size**: `163` lines (`6350` bytes)

**Functions:**
- `def manifest_fingerprint(requests)` - *Hash the validated requests so a changed manifest cannot reuse old progress.*
- `def state_path(output_dir, fingerprint)`
- `def load_state(path, fingerprint)` - *Load a batch state file, keyed by 1-based track index.*
- `def save_state(path, fingerprint, entries)` - *Write progress atomically so a crash leaves the last completed track reusable.*

---

### [`muse/catalog.py`](muse/catalog.py)
> *Read-only discovery of scored artifacts under an output directory.*

**Size**: `205` lines (`7083` bytes)

**Classes:**
- `class Artifact`
  - Method `.as_dict()`

**Functions:**
- `def load_artifacts(output_dir, accepted_only, limit, match, sort)` - *Scan one output directory level and return scored artifacts plus warnings.*
- `def load_artifact(path)` - *Read and validate one metadata file, returning the summary and raw payload.*
- `def _read_metadata(path)`
- `def _entry(metadata, payload)`
- `def _text(value)`

---

### [`muse/cli.py`](muse/cli.py)
> *Command line interface: generate, batch, judge, inspect providers.*

**Size**: `765` lines (`29716` bytes)

**Functions:**
- `def main(argv, *, config, provider, judge)`
- `def build_parser()`
- `def _attempt_count(value)`
- `def _positive_count(value)`
- `def _add_attempts(parser)`
- `def _common(parser)`
- `def _settings(args, config)`
- `def _generate(args, settings, provider, judge)`
- `def _batch(args, settings, provider, judge)`
- `def _dry_run(args, settings, requests, forced)`
- `def _judge(args, settings, judge)`
- `def _doctor(args, settings)`
- `def _catalog(args, settings)`
- `def _show(args, settings)`
- `def _resolve_artifact(value, output_dir)`
- `def _print_artifact(entry, payload)`
- `def _providers(args)`
- `def _result_payload(result)`
- `def _attempt_payload(attempt)`
- `def _batch_payload(entries)`
- `def _filled(entries)`
- `def _evidence_exists(entry)`
- `def _result_entry(index, request, result)`
- `def _failed_entry(index, request, exc)`
- `def _print_batch_track(index, total, request, result)`
- `def _verdict_payload(verdict, path)`
- `def _verdict_dict(verdict)`
- `def _print_result(result)`
- `def _print_verdict(verdict)`

---

### [`muse/config.py`](muse/config.py)
> *Configuration resolved from explicit values, environment variables and defaults.*

**Size**: `135` lines (`5312` bytes)

**Classes:**
- `class MuseConfig`
  - Method `.__post_init__()`
  - Method `.from_env(env)`
  - Method `.with_overrides(**changes)`
  - Method `.replicate_token()`
  - Method `.gemini_key()`

**Functions:**
- `def _text(source, key, default)`
- `def _int(raw, default, name)`
- `def _float(raw, default, name)`

---

### [`muse/doctor.py`](muse/doctor.py)
> *Read-only local configuration checks for the doctor command.*

**Size**: `112` lines (`3133` bytes)

**Classes:**
- `class Check`
  - Method `.as_dict()`

**Functions:**
- `def run_checks(config)`
- `def _python_check()`
- `def _output_check(output_dir)`
- `def _provider_check(settings)`
- `def _judge_check(settings)`
- `def _key_checks(settings)`

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

**Size**: `196` lines (`8217` bytes)

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

**Size**: `56` lines (`2063` bytes)

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

**Size**: `181` lines (`7228` bytes)

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

**Size**: `263` lines (`8722` bytes)

**Functions:**
- `def compose(request, config, provider, judge, require_judge, max_attempts)`
- `def judge_track(track, request, config, judge)`
- `def revise_prompt(prompt, verdict)` - *Append the judge's actionable suggestions without repeating or overlong text.*
- `def _validate_attempts(max_attempts)`
- `def _render_and_judge(request, settings, engine, judge, require_judge, number, planned)`
- `def _listen(track, request, settings, judge, require_judge)`
- `def _metadata(request, track, verdict, judge_error, settings, number, planned)`
- `def _record_history(best, attempts, settings)`
- `def _attempt_summary(attempt, settings)`
- `def _display_path(path, root)`

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

**Size**: `137` lines (`5435` bytes)

**Classes:**
- `class ReplicateMusicProvider`
  - Method `.__init__(config, http, sleep, poll_interval, clock)`
  - Method `.generate(request, destination)`
  - Method `._create(request)`
  - Method `._wait(created)`
  - Method `._output_url(final)`

---

### [`muse/types.py`](muse/types.py)
> *Public data types shared by providers, judges and the pipeline.*

**Size**: `137` lines (`4440` bytes)

**Classes:**
- `class MusicRequest` - *A prompt plus the theme it must serve.*
  - Method `.__post_init__()`
  - Property `.intent` - *The theme when given, else the prompt.*
  - Property `.label`
- `class Track`
- `class Verdict`
  - Method `.__post_init__()`
  - Property `.accepted`
- `class Attempt` - *One rendered take and the verdict that judged it.*
  - Property `.accepted`
  - Property `.score`
- `class CompositionResult`
  - Property `.accepted`

---

### [`tests/__init__.py`](tests/__init__.py)
> *Regression shield for Muse.*

**Size**: `1` lines (`34` bytes)

---

### [`tests/test_audio.py`](tests/test_audio.py)
**Size**: `90` lines (`4051` bytes)

**Classes:**
- `class SlugTests`
  - Method `.test_slugifies_prompt()`
  - Method `.test_falls_back_when_nothing_remains()`
  - Method `.test_avoids_windows_reserved_device_names()`
- `class MimeTests`
  - Method `.test_known_and_unknown_suffixes()`
- `class ToneTests`
  - Method `.test_writes_a_readable_wav()`
  - Method `.test_duration_of_non_wav_is_none()`
- `class ArtifactTests`
  - Method `.test_unique_directories_get_suffixes()`
  - Method `.test_unwritable_parent_is_a_muse_error()`
  - Method `.test_json_write_leaves_no_temp_file()`
  - Method `.test_failed_json_write_keeps_the_previous_file_and_no_temp()`
  - Method `.test_storage_failure_is_a_muse_error()`

---

### [`tests/test_batch.py`](tests/test_batch.py)
**Size**: `628` lines (`27598` bytes)

**Classes:**
- `class CountingProvider`
  - Method `.__init__(inner)`
  - Method `.generate(request, destination)`
- `class FlakyProvider`
  - Method `.__init__(inner, fail_prompt)`
  - Method `.generate(request, destination)`
- `class ManifestTests`
  - Method `.setUp()`
  - Method `.write(payload)`
  - Method `.test_loads_tracks_with_defaults()`
  - Method `.test_missing_file_is_explained()`
  - Method `.test_invalid_json_is_explained_with_position()`
  - Method `.test_root_and_track_shape_are_checked()`
  - Method `.test_unknown_track_keys_and_bad_values_are_rejected()`
  - Method `.test_overflowing_duration_is_rejected()`
  - Method `.test_track_count_is_capped()`
  - Method `.test_manifest_size_is_capped()`
  - Method `.test_utf8_bom_is_accepted()`
- `class BatchStateTests`
  - Method `.setUp()`
  - Method `.test_fingerprint_is_stable_and_sensitive()`
  - Method `.test_state_round_trip()`
  - Method `.test_missing_or_mismatched_state_is_explained()`
  - Method `.test_corrupt_state_is_explained()`
  - Method `.test_inconsistent_state_is_explained()`
  - Method `.test_state_size_is_capped()`
  - Method `.test_boolean_schema_is_rejected()`
- `class BatchCliTests`
  - Method `.setUp()`
  - Method `.manifest(tracks)`
  - Method `.run_cli(argv, judge, provider)`
  - Method `.test_batch_json_renders_every_track()`
  - Method `.test_batch_human_output_and_strict_exit()`
  - Method `.test_batch_applies_attempts_per_track()`
  - Method `.test_batch_preflights_the_judge_before_state()`
  - Method `.test_batch_without_a_judge_is_refused()`
  - Method `.test_batch_missing_manifest_exits_one()`
  - Method `.test_batch_dry_run_json_makes_no_calls()`
  - Method `.test_batch_dry_run_human_output_without_a_judge()`
  - Method `.test_dry_run_resume_previews_reuse_and_retry()`
  - Method `.test_dry_run_resume_without_state_is_refused()`
  - Method `.test_dry_run_resume_marks_missing_evidence()`
  - Method `.state_file()`
  - Method `.test_batch_writes_state_after_each_track()`
  - Method `.test_resume_of_all_accepted_tracks_needs_no_judge_key()`
  - Method `.test_resume_of_all_accepted_tracks_allows_judge_none()`
  - Method `.test_force_rerenders_an_accepted_track()`
  - Method `.test_force_requires_resume()`
  - Method `.test_force_rejects_an_unknown_name()`
  - Method `.test_dry_run_resume_force_marks_render()`
  - Method `.test_resume_reuses_accepted_tracks()`
  - Method `.test_resume_rerenders_rejected_tracks()`
  - Method `.test_resume_without_state_is_refused()`
  - Method `.test_keep_going_records_failure_and_resume_finishes()`
  - Method `.test_resume_rerenders_when_evidence_is_missing()`

---

### [`tests/test_catalog.py`](tests/test_catalog.py)
**Size**: `296` lines (`12289` bytes)

**Classes:**
- `class CatalogTests`
  - Method `.setUp()`
  - Method `.test_reads_filters_and_limits()`
  - Method `.test_sorts_newest_first()`
  - Method `.test_skips_corrupt_oversized_and_unknown_schema()`
  - Method `.test_schema_one_and_missing_audio()`
  - Method `.test_counts_attempt_history()`
  - Method `.test_filters_by_case_insensitive_text()`
  - Method `.test_sorts_by_score_and_name()`
  - Method `.test_rejects_windows_separator_in_file_name()`
  - Method `.test_limit_must_be_positive_when_given()`
- `class ListCliTests`
  - Method `.setUp()`
  - Method `.run_cli(argv)`
  - Method `.test_list_json()`
  - Method `.test_list_filters_and_limits()`
  - Method `.test_list_match_and_sort()`
  - Method `.test_list_invalid_sort_is_misuse()`
  - Method `.test_list_empty_and_corrupt()`
  - Method `.test_list_limit_zero_is_misuse()`
- `class ShowCliTests`
  - Method `.setUp()`
  - Method `.run_cli(argv)`
  - Method `.test_show_human_and_json()`
  - Method `.test_show_accepts_a_folder_or_metadata_path()`
  - Method `.test_show_marks_missing_audio()`
  - Method `.test_show_missing_and_corrupt()`

**Functions:**
- `def write_artifact(root, folder, *, schema, accepted, score, verdict, created, audio)`

---

### [`tests/test_cli.py`](tests/test_cli.py)
**Size**: `225` lines (`8708` bytes)

**Classes:**
- `class ScriptedJudge`
  - Method `.__init__(verdicts)`
  - Method `.judge(track, request)`
- `class CliTests`
  - Method `.setUp()`
  - Method `.run_cli(argv, judge)`
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
  - Method `.test_allow_unjudged_missing_key_exits_zero()`
  - Method `.test_filesystem_failure_is_explained()`
  - Method `.test_attempts_json_reports_every_take()`
  - Method `.test_attempts_human_output_lists_takes()`
  - Method `.test_attempts_out_of_range_is_misuse()`
  - Method `.test_attempts_with_judge_none_is_explained()`

**Functions:**
- `def verdict(score, kind, suggestions)`

---

### [`tests/test_doctor.py`](tests/test_doctor.py)
**Size**: `123` lines (`5073` bytes)

**Classes:**
- `class DoctorTests`
  - Method `.setUp()`
  - Method `.config(**changes)`
  - Method `.checks(config)`
  - Method `.test_mock_configuration_is_healthy()`
  - Method `.test_required_keys_are_reported()`
  - Method `.test_output_file_is_reported()`
  - Method `.test_unknown_adapter_names_are_reported()`
  - Method `.test_invalid_configuration_is_a_single_finding()`
- `class DoctorCliTests`
  - Method `.setUp()`
  - Method `.run_cli(argv, config)`
  - Method `.test_doctor_json_healthy()`
  - Method `.test_doctor_cli_overrides_the_environment()`
  - Method `.test_doctor_reports_missing_keys()`
  - Method `.test_doctor_reports_output_file()`

---

### [`tests/test_judges.py`](tests/test_judges.py)
**Size**: `161` lines (`7053` bytes)

**Classes:**
- `class FakeHttp`
  - Method `.__init__(response)`
  - Method `.json(method, url, payload, headers)`
- `class GeminiTests`
  - Method `.setUp()`
  - Method `.test_sends_audio_and_returns_verdict()`
  - Method `.test_invalid_score_is_rejected()`
  - Method `.test_boolean_score_is_rejected()`
  - Method `.test_unknown_verdict_is_rejected()`
  - Method `.test_missing_candidate_is_rejected()`
  - Method `.test_non_object_reply_is_rejected()`
  - Method `.test_malformed_candidate_is_rejected()`
  - Method `.test_oversized_audio_is_rejected_before_upload()`
  - Method `.test_oversized_audio_is_rejected_before_reading()`
  - Method `.test_unreadable_track_is_explained()`
  - Method `.test_empty_verdict_text_is_rejected()`
- `class MockJudgeTests`
  - Method `.setUp()`
  - Method `.track()`
  - Method `.test_shared_terms_fit()`
  - Method `.test_disjoint_terms_miss()`
  - Method `.test_disjoint_terms_suggest_the_theme_words()`
  - Method `.test_missing_theme_is_partial()`
- `class JudgeRegistryTests`
  - Method `.test_unknown_judge_is_explained()`
  - Method `.test_mock_judge_is_pickable()`

**Functions:**
- `def reply(**changes)`

---

### [`tests/test_net.py`](tests/test_net.py)
**Size**: `201` lines (`8700` bytes)

**Classes:**
- `class FlakyClient`
  - Method `.__init__(responses)`
  - Method `._once(method, url, body, headers)`
- `class BrokenClient`
  - Method `.__init__()`
  - Method `._once(method, url, body, headers)`
- `class HttpClientTests`
  - Method `.test_retries_retryable_status()`
  - Method `.test_does_not_retry_client_error()`
  - Method `.test_retries_are_exhausted()`
  - Method `.test_non_json_body_is_explained()`
  - Method `.test_truncated_json_response_is_retried()`
  - Method `.test_unserializable_payload_is_explained()`
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
  - Method `.test_download_rejects_non_http_urls()`
  - Method `.test_download_rejects_an_empty_file()`
  - Method `.test_truncated_download_is_retried_and_cleaned()`
  - Method `.test_download_size_is_capped()`
  - Method `.test_download_folder_failure_is_explained()`

---

### [`tests/test_pipeline.py`](tests/test_pipeline.py)
**Size**: `333` lines (`13422` bytes)

**Classes:**
- `class FailingJudge`
  - Method `.judge(track, request)`
- `class FailingProvider`
  - Method `.generate(request, destination)`
- `class CountingProvider`
  - Method `.__init__(inner)`
  - Method `.generate(request, destination)`
- `class ScriptedJudge`
  - Method `.__init__(verdicts)`
  - Method `.judge(track, request)`
- `class PipelineTests`
  - Method `.setUp()`
  - Method `.test_compose_writes_audio_verdict_and_metadata()`
  - Method `.test_second_composition_gets_a_unique_folder()`
  - Method `.test_judge_none_skips_listening()`
  - Method `.test_required_judge_failure_raises_but_keeps_evidence()`
  - Method `.test_optional_judge_failure_keeps_audio()`
  - Method `.test_required_judge_is_built_before_rendering()`
  - Method `.test_allow_unjudged_renders_when_the_judge_cannot_be_built()`
  - Method `.test_tokens_never_reach_metadata()`
  - Method `.test_failed_generation_removes_empty_run_folder()`
  - Method `.test_judge_track_uses_injected_judge()`
  - Method `.test_attempts_stop_after_acceptance()`
  - Method `.test_rejected_track_is_retried_with_judge_suggestions()`
  - Method `.test_history_read_failure_is_a_muse_error()`
  - Method `.test_best_attempt_wins_when_none_are_accepted()`
  - Method `.test_attempts_stop_when_the_judge_offers_no_suggestions()`
  - Method `.test_attempts_without_a_judge_are_refused()`
  - Method `.test_attempt_count_is_bounded()`
  - Method `.test_mock_judge_refinement_reaches_fit_offline()`
- `class RevisePromptTests`
  - Method `.test_returns_the_prompt_when_nothing_is_actionable()`
  - Method `.test_appends_distinct_suggestions_once()`
  - Method `.test_keeps_the_prompt_within_the_limit()`

**Functions:**
- `def verdict(score, kind, suggestions)`

---

### [`tests/test_providers.py`](tests/test_providers.py)
**Size**: `208` lines (`8718` bytes)

**Classes:**
- `class FakeHttp`
  - Method `.__init__(responses)`
  - Method `.json(method, url, payload, headers)`
  - Method `.download(url, destination, headers)`
- `class SlowHttp`
  - Method `.__init__(responses, clock)`
  - Method `.json(method, url, payload, headers)`
- `class ReplicateTests`
  - Method `.setUp()`
  - Method `.test_official_model_flow()`
  - Method `.test_pinned_version_uses_predictions_endpoint()`
  - Method `.test_failed_prediction_is_reported()`
  - Method `.test_timeout_is_reported()`
  - Method `.test_slow_polls_respect_the_wall_clock_budget()`
  - Method `.test_last_poll_can_be_the_success()`
  - Method `.test_empty_output_is_reported()`
  - Method `.test_missing_handle_is_reported()`
  - Method `.test_malformed_handle_is_reported()`
  - Method `.test_malformed_poll_response_is_reported()`
  - Method `.test_poll_interval_must_be_positive()`
- `class RegistryTests`
  - Method `.test_mock_provider_is_pickable()`
  - Method `.test_unknown_provider_is_explained()`
  - Method `.test_mock_provider_writes_a_file()`

**Functions:**
- `def config(**changes)`

---

### [`tests/test_types.py`](tests/test_types.py)
**Size**: `206` lines (`8413` bytes)

**Classes:**
- `class MusicRequestTests`
  - Method `.test_theme_defaults_to_prompt_intent()`
  - Method `.test_theme_wins_as_intent()`
  - Method `.test_empty_prompt_is_rejected()`
  - Method `.test_duration_bounds()`
  - Method `.test_text_fields_must_be_strings()`
  - Method `.test_duration_must_be_a_finite_number()`
  - Method `.test_duration_is_stored_as_float()`
  - Method `.test_label_prefers_name_then_theme()`
- `class VerdictTests`
  - Method `.test_accepts_at_threshold()`
  - Method `.test_rejects_below_threshold()`
  - Method `.test_invalid_values_are_rejected()`
  - Method `.test_sequences_are_normalized_and_validated()`
- `class ConfigTests`
  - Method `.test_defaults()`
  - Method `.test_environment_overrides()`
  - Method `.test_empty_environment_values_fall_back_to_defaults()`
  - Method `.test_environment_text_is_trimmed_and_expanded()`
  - Method `.test_invalid_number_is_a_configuration_error()`
  - Method `.test_threshold_outside_percent_is_rejected()`
  - Method `.test_non_positive_timeouts_are_rejected()`
  - Method `.test_non_finite_or_wrongly_typed_values_are_rejected()`
  - Method `.test_output_dir_accepts_a_string()`
  - Method `.test_missing_tokens_are_explained()`
  - Method `.test_tokens_are_not_in_repr()`
- `class PackagingTests`
  - Method `.test_pyproject_version_matches_the_module()`

---
