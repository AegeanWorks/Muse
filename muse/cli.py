"""Command line interface: generate, batch, judge, inspect providers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .audio import wav_duration
from .batch import load_manifest
from .batch_state import load_state, manifest_fingerprint, save_state, state_path
from .config import MuseConfig
from .errors import ConfigurationError, MuseError
from .judges.base import MusicJudge
from .judges.registry import judges
from .pipeline import compose, judge_track
from .providers.base import MusicProvider
from .providers.registry import providers
from .types import MAX_ATTEMPTS, MAX_DURATION, Attempt, CompositionResult, MusicRequest, Track, Verdict


def main(
    argv: Sequence[str] | None = None,
    *,
    config: MuseConfig | None = None,
    provider: MusicProvider | None = None,
    judge: MusicJudge | None = None,
) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    try:
        settings = _settings(args, config)
        if args.command == "generate":
            return _generate(args, settings, provider, judge)
        if args.command == "batch":
            return _batch(args, settings, provider, judge)
        if args.command == "judge":
            return _judge(args, settings, judge)
        return _providers(args)
    except MuseError as exc:
        print(exc.render(), file=sys.stderr)
        return 1
    except OSError as exc:
        print(
            f"Error: a filesystem operation failed: {exc}\n"
            "Why: an output path, audio file or state file could not be read or written.\n"
            "Fix: check free disk space and folder permissions, then retry.",
            file=sys.stderr,
        )
        return 1
    except ValueError as exc:
        print(
            f"Error: invalid request: {exc}\n"
            "Why: the prompt or duration is outside what a music model accepts.\n"
            f"Fix: pass a non-empty prompt and a duration between 0 and {MAX_DURATION:g} seconds.",
            file=sys.stderr,
        )
        return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="muse",
        description="Generate themed music with a hosted model, then let a judge listen and score it.",
        epilog="Example: python -m muse generate \"dark ambient cavern\" --theme \"underground cave level\" --duration 30",
    )
    parser.add_argument("--version", action="version", version=f"muse {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="render a track and judge its theme fit")
    generate.add_argument("prompt", help="what the music should sound like")
    generate.add_argument("--theme", default="", help="project theme the track must serve")
    generate.add_argument("--duration", type=float, default=30.0, help="seconds, up to 190")
    generate.add_argument("--name", default="", help="artifact folder name")
    _add_attempts(generate)
    _common(generate)
    generate.add_argument("--strict", action="store_true", help="exit 1 when the verdict is missing or below threshold")
    generate.add_argument(
        "--allow-unjudged",
        action="store_true",
        help="keep the audio and metadata when the judge fails",
    )

    batch = subparsers.add_parser("batch", help="render and judge every track in a JSON manifest")
    batch.add_argument("manifest", type=Path, help="JSON file with a tracks array")
    _add_attempts(batch)
    _common(batch)
    batch.add_argument("--strict", action="store_true", help="exit 1 when any track is rejected")
    batch.add_argument("--resume", action="store_true", help="reuse accepted tracks from the saved batch state")
    batch.add_argument(
        "--keep-going",
        action="store_true",
        help="record a failed track and continue with the rest of the manifest",
    )
    batch.add_argument(
        "--dry-run",
        action="store_true",
        help="validate the manifest and print the plan without rendering",
    )

    judge = subparsers.add_parser("judge", help="score an existing audio file against a theme")
    judge.add_argument("audio", help="path to a wav, mp3, ogg or flac file")
    judge.add_argument("--theme", required=True, help="project theme the track must serve")
    judge.add_argument("--prompt", default="", help="the prompt that produced the track")
    _common(judge)
    judge.add_argument("--strict", action="store_true", help="exit 1 when the score is below threshold")

    listing = subparsers.add_parser("providers", help="list music providers and judges")
    listing.add_argument("--json", action="store_true", help="machine-readable output")
    return parser


def _attempt_count(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("attempts must be a whole number") from exc
    if not 1 <= number <= MAX_ATTEMPTS:
        raise argparse.ArgumentTypeError(f"attempts must be between 1 and {MAX_ATTEMPTS}")
    return number


def _add_attempts(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--attempts",
        type=_attempt_count,
        default=1,
        metavar="N",
        help=f"render up to N takes per track, folding judge suggestions into the next prompt (default 1, max {MAX_ATTEMPTS})",
    )


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--out", type=Path, default=None, help="artifact directory (default: output)")
    parser.add_argument("--provider", default=None, help="music provider name")
    parser.add_argument("--model", default=None, help="provider model slug")
    parser.add_argument("--judge", default=None, help="judge name, or 'none'")
    parser.add_argument("--judge-model", default=None, help="judge model name")
    parser.add_argument("--min-score", type=int, default=None, help="acceptance threshold 0-100")
    parser.add_argument("--json", action="store_true", help="machine-readable output")


def _settings(args: argparse.Namespace, config: MuseConfig | None) -> MuseConfig:
    base = config or MuseConfig.from_env()
    return base.with_overrides(
        output_dir=getattr(args, "out", None),
        provider=getattr(args, "provider", None),
        music_model=getattr(args, "model", None),
        judge=getattr(args, "judge", None),
        judge_model=getattr(args, "judge_model", None),
        min_score=getattr(args, "min_score", None),
    )


def _generate(
    args: argparse.Namespace,
    settings: MuseConfig,
    provider: MusicProvider | None,
    judge: MusicJudge | None,
) -> int:
    request = MusicRequest(
        prompt=args.prompt,
        theme=args.theme,
        duration=args.duration,
        name=args.name,
    )
    result = compose(
        request,
        settings,
        provider=provider,
        judge=judge,
        require_judge=not args.allow_unjudged,
        max_attempts=args.attempts,
    )
    if args.json:
        print(json.dumps(_result_payload(result), indent=2))
    else:
        _print_result(result)
    return 1 if args.strict and not result.accepted else 0


def _batch(
    args: argparse.Namespace,
    settings: MuseConfig,
    provider: MusicProvider | None,
    judge: MusicJudge | None,
) -> int:
    requests = load_manifest(args.manifest)
    if args.dry_run:
        return _dry_run(args, settings, requests)
    if settings.judge == "none" and judge is None:
        raise ConfigurationError(
            "batch needs a listening judge",
            "a batch only reports accepted tracks when a judge scores every take",
            "omit --judge none, or pass --judge gemini or --judge mock",
        )
    fingerprint = manifest_fingerprint(requests)
    progress = state_path(settings.output_dir, fingerprint)
    previous = load_state(progress, fingerprint) if args.resume else {}
    entries: list[dict[str, Any] | None] = [previous.get(index) for index in range(1, len(requests) + 1)]
    if not args.resume:
        save_state(progress, fingerprint, [])
    for index, request in enumerate(requests, 1):
        prior = previous.get(index)
        if args.resume and prior is not None and prior["status"] == "accepted":
            if _evidence_exists(prior):
                entry = dict(prior)
                entry["reused"] = True
                entries[index - 1] = entry
                if not args.json:
                    audio = entry["payload"].get("audio")
                    print(f"[{index}/{len(requests)}] {request.label}: reused accepted take -> {audio}")
                continue
            print(
                f"Warning: evidence for {request.label} is missing; rendering it again.",
                file=sys.stderr,
            )
        try:
            result = compose(
                request,
                settings,
                provider=provider,
                judge=judge,
                max_attempts=args.attempts,
            )
        except MuseError as exc:
            entries[index - 1] = _failed_entry(index, request, exc)
            save_state(progress, fingerprint, _filled(entries))
            if not args.keep_going:
                raise
            if not args.json:
                print(f"[{index}/{len(requests)}] {request.label}: failed ({exc.what})")
            continue
        entries[index - 1] = _result_entry(index, request, result)
        save_state(progress, fingerprint, _filled(entries))
        if not args.json:
            _print_batch_track(index, len(requests), request, result)
    save_state(progress, fingerprint, _filled(entries))
    payload = _batch_payload(_filled(entries))
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Batch: {payload['accepted']}/{payload['total']} accepted")
        if payload["rejected"]:
            names = [entry["name"] for entry in _filled(entries) if entry["status"] == "rejected"]
            print(f"Rejected: {', '.join(names)}")
        if payload["failed"]:
            names = [entry["name"] for entry in _filled(entries) if entry["status"] == "failed"]
            print(f"Failed: {', '.join(names)}")
        if payload["reused"]:
            print(f"Reused: {payload['reused']}")
    return 1 if payload["failed"] or (args.strict and payload["rejected"]) else 0


def _dry_run(
    args: argparse.Namespace,
    settings: MuseConfig,
    requests: tuple[MusicRequest, ...],
) -> int:
    tracks = [
        {
            "name": request.label,
            "prompt": request.prompt,
            "theme": request.theme,
            "duration": request.duration,
        }
        for request in requests
    ]
    payload = {
        "dry_run": True,
        "tracks": tracks,
        "total": len(tracks),
        "attempts": args.attempts,
        "provider": settings.provider,
        "judge": settings.judge,
        "output": str(settings.output_dir),
    }
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0
    print(
        f"Dry run: {len(tracks)} track(s), up to {args.attempts} take(s) each "
        f"-> {settings.output_dir}"
    )
    for index, request in enumerate(requests, 1):
        intent = request.theme or "(prompt only)"
        print(f"[{index}/{len(requests)}] {request.label}: {request.duration:g}s, theme {intent}")
    print("No provider or judge was called.")
    return 0


def _judge(args: argparse.Namespace, settings: MuseConfig, judge: MusicJudge | None) -> int:
    path = Path(args.audio)
    if not path.is_file():
        raise MuseError(
            f"audio file not found: {path}",
            "the judge can only listen to an existing file",
            "pass the path printed by `muse generate` or correct the filename",
        )
    if settings.judge == "none" and judge is None:
        raise ConfigurationError(
            "the judge command needs a listening judge",
            "'none' disables listening, so there is nothing to score the file",
            "omit --judge none, or pass --judge gemini or --judge mock",
        )
    duration = wav_duration(path) or 30.0
    request = MusicRequest(
        prompt=args.prompt or args.theme,
        theme=args.theme,
        duration=min(max(duration, 0.1), MAX_DURATION),
        name=path.stem,
    )
    track = Track(
        path=path,
        provider="file",
        model="local file",
        duration_seconds=request.duration,
        prompt=request.prompt,
        theme=request.theme,
    )
    verdict = judge_track(track, request, settings, judge)
    if args.json:
        print(json.dumps(_verdict_payload(verdict, path), indent=2))
    else:
        _print_verdict(verdict)
    return 1 if args.strict and not verdict.accepted else 0


def _providers(args: argparse.Namespace) -> int:
    payload = {"providers": providers(), "judges": judges()}
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0
    for title, entries in (("Music providers", payload["providers"]), ("Judges", payload["judges"])):
        print(f"{title}:")
        for name, description in entries.items():
            print(f"  {name:<10} {description}")
    return 0


def _result_payload(result: CompositionResult) -> dict[str, Any]:
    return {
        "audio": str(result.track.path),
        "metadata": str(result.metadata_path),
        "provider": result.track.provider,
        "model": result.track.model,
        "duration_seconds": result.track.duration_seconds,
        "verdict": None if result.verdict is None else _verdict_dict(result.verdict),
        "accepted": result.accepted,
        "judge_error": result.judge_error,
        "attempts": [_attempt_payload(attempt) for attempt in result.attempts],
    }


def _attempt_payload(attempt: Attempt) -> dict[str, Any]:
    return {
        "number": attempt.number,
        "prompt": attempt.prompt,
        "audio": str(attempt.track.path),
        "metadata": str(attempt.metadata_path),
        "score": attempt.score,
        "verdict": None if attempt.verdict is None else attempt.verdict.verdict,
        "accepted": attempt.accepted,
    }


def _batch_payload(entries: list[dict[str, Any]]) -> dict[str, Any]:
    tracks = []
    for entry in entries:
        payload = dict(entry.get("payload") or {})
        payload["reused"] = bool(entry.get("reused"))
        tracks.append(payload)
    return {
        "tracks": tracks,
        "total": len(tracks),
        "accepted": sum(1 for track in tracks if track.get("accepted")),
        "rejected": sum(1 for entry in entries if entry["status"] == "rejected"),
        "failed": sum(1 for entry in entries if entry["status"] == "failed"),
        "reused": sum(1 for entry in entries if entry.get("reused")),
    }


def _filled(entries: list[dict[str, Any] | None]) -> list[dict[str, Any]]:
    return [entry for entry in entries if entry is not None]


def _evidence_exists(entry: dict[str, Any]) -> bool:
    payload = entry.get("payload")
    if not isinstance(payload, dict):
        return False
    for key in ("audio", "metadata"):
        value = payload.get(key)
        if not isinstance(value, str):
            return False
        candidate = Path(value)
        try:
            if not candidate.is_file() or candidate.stat().st_size == 0:
                return False
        except OSError:
            return False
    return True


def _result_entry(index: int, request: MusicRequest, result: CompositionResult) -> dict[str, Any]:
    payload = {"name": request.label, "prompt": request.prompt, "theme": request.theme}
    payload.update(_result_payload(result))
    return {
        "index": index,
        "name": request.label,
        "prompt": request.prompt,
        "theme": request.theme,
        "status": "accepted" if result.accepted else "rejected",
        "payload": payload,
        "error": None,
    }


def _failed_entry(index: int, request: MusicRequest, exc: MuseError) -> dict[str, Any]:
    error = exc.what
    payload = {
        "name": request.label,
        "prompt": request.prompt,
        "theme": request.theme,
        "audio": None,
        "metadata": None,
        "provider": None,
        "model": None,
        "duration_seconds": request.duration,
        "verdict": None,
        "accepted": False,
        "judge_error": None,
        "attempts": [],
        "error": error,
    }
    return {
        "index": index,
        "name": request.label,
        "prompt": request.prompt,
        "theme": request.theme,
        "status": "failed",
        "payload": payload,
        "error": error,
    }


def _print_batch_track(
    index: int,
    total: int,
    request: MusicRequest,
    result: CompositionResult,
) -> None:
    if result.verdict is None:
        score = "unjudged"
    else:
        score = f"{result.verdict.score}/100 {result.verdict.verdict}"
    takes = len(result.attempts)
    label = "take" if takes == 1 else "takes"
    print(f"[{index}/{total}] {request.label}: {score} ({takes} {label}) -> {result.track.path}")


def _verdict_payload(verdict: Verdict, path: Path) -> dict[str, Any]:
    return {"audio": str(path), "verdict": _verdict_dict(verdict), "accepted": verdict.accepted}


def _verdict_dict(verdict: Verdict) -> dict[str, Any]:
    return {
        "score": verdict.score,
        "verdict": verdict.verdict,
        "summary": verdict.summary,
        "strengths": list(verdict.strengths),
        "issues": list(verdict.issues),
        "suggestions": list(verdict.suggestions),
        "judge": verdict.judge,
        "model": verdict.model,
        "threshold": verdict.threshold,
    }


def _print_result(result: CompositionResult) -> None:
    if len(result.attempts) > 1:
        print("Attempts:")
        for attempt in result.attempts:
            if attempt.verdict is None:
                label = "none"
            else:
                label = f"{attempt.verdict.score}/100 {attempt.verdict.verdict}"
            marker = " <- selected" if attempt.metadata_path == result.metadata_path else ""
            print(f"  {attempt.number}. {label}  {attempt.track.path}{marker}")
    print(f"Rendered: {result.track.path} ({result.track.duration_seconds:g}s, {result.track.provider}/{result.track.model})")
    print(f"Metadata: {result.metadata_path}")
    if result.verdict is None:
        reason = f" ({result.judge_error})" if result.judge_error else ""
        print(f"Verdict: none{reason}")
        return
    _print_verdict(result.verdict)


def _print_verdict(verdict: Verdict) -> None:
    print(f"Verdict: {verdict.score}/100 {verdict.verdict} (threshold {verdict.threshold})")
    print(f"Summary: {verdict.summary}")
    if verdict.strengths:
        print("Strengths:")
        for strength in verdict.strengths:
            print(f"  - {strength}")
    if verdict.issues:
        print("Issues:")
        for issue in verdict.issues:
            print(f"  - {issue}")
    if verdict.suggestions:
        print("Suggestions:")
        for suggestion in verdict.suggestions:
            print(f"  - {suggestion}")
    print(f"Accepted: {'yes' if verdict.accepted else 'no'}")
