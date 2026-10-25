"""User-facing failures with what, why and how to fix them."""

from __future__ import annotations


class MuseError(Exception):
    def __init__(self, what: str, why: str, fix: str) -> None:
        super().__init__(what)
        self.what = what
        self.why = why
        self.fix = fix

    def render(self) -> str:
        return f"Error: {self.what}\nWhy: {self.why}\nFix: {self.fix}"


class ConfigurationError(MuseError):
    pass


class GenerationError(MuseError):
    pass


class JudgeError(MuseError):
    pass
