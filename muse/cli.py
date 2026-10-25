"""Command line interface: generate, judge, inspect providers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .audio import wav_duration
from .config import MuseConfig
from .errors import ConfigurationError, MuseError
from .judges.base import MusicJudge
from .judges.registry import judges
from .pipeline import compose, judge_track
from .providers.base import MusicProvider
from .providers.registry import providers
from .types import MAX_DURATION, CompositionResult, MusicRequest, Track, Verdict


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
        if args.command == "judge":
            return _judge(args, settings, judge)
        return _providers(args)
    except MuseError as exc:
        print(exc.render(), file=sys.stderr)
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
    _common(generate)
    generate.add_argument("--strict", action="store_true", help="exit 1 when the verdict is missing or below threshold")
    generate.add_argument(
        "--allow-unjudged",
        action="store_true",
        help="keep the audio and metadata when the judge fails",
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
    )
    if args.json:
        print(json.dumps(_result_payload(result), indent=2))
    else:
        _print_result(result)
    return 1 if args.strict and not result.accepted else 0


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
    }


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
