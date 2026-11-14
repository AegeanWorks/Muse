"""Streaming sample-rate conversion with an anti-alias filter when downsampling.

Downsampling without a filter folds every tone above the new Nyquist frequency back into the
band at nearly full level. Here each output sample is a windowed-sinc low-pass of the source
samples around it. Positions are exact integers, so the result does not depend on how the input
is split into chunks, and memory stays bounded.
"""

from __future__ import annotations

import math
import operator
from math import gcd
from typing import Iterable, Iterator, Sequence

# The -6 dB point as a fraction of the target rate: flat to 0.40, rejecting from 0.50 upward.
CUTOFF = 0.45
# Kaiser beta 5 with this many taps per unit of source/target rate ratio gives at least 55 dB of
# rejection across the whole alias band (measured in the design spike and pinned by tests).
TAPS_PER_RATIO = 17
KAISER_BETA = 5.0
# Kernel tables hold one kernel per fractional position; beyond this many, positions are rounded
# to the nearest 1/MAX_PHASES of a sample (an error far below the filter's own tolerance).
MAX_PHASES = 1024


def _dot_fallback(first: Sequence[float], second: Sequence[float]) -> float:
    return sum(map(operator.mul, first, second))


# math.sumprod runs the multiply-add loop in C (Python 3.12+); older versions use the fallback.
_dot = getattr(math, "sumprod", _dot_fallback)


def resample_chunks(
    chunks: Iterable[list[float]], source_rate: int, target_rate: int
) -> Iterator[list[float]]:
    """Convert a stream of mono sample blocks from `source_rate` to `target_rate`."""
    if source_rate == target_rate:
        yield from chunks
    elif target_rate > source_rate:
        yield from _linear(chunks, source_rate, target_rate)
    else:
        yield from _lowpass(chunks, source_rate, target_rate)


def tap_count(source_rate: int, target_rate: int) -> int:
    """Even number of filter taps for a downsampling ratio."""
    return 2 * max(1, round(TAPS_PER_RATIO * source_rate / target_rate))


def lowpass_kernel(taps: int, cutoff: float, fraction: float) -> list[float]:
    """Kaiser-windowed sinc for a position `fraction` of a sample past a source sample.

    `cutoff` is in cycles per source sample. The kernel is normalised to unit gain at 0 Hz.
    """
    half = taps // 2
    denominator = _bessel_i0(KAISER_BETA)
    values: list[float] = []
    for offset in range(-half + 1, half + 1):
        distance = offset - fraction
        ratio = distance / half
        if abs(ratio) >= 1.0:
            values.append(0.0)
            continue
        sinc = 2 * cutoff if distance == 0 else math.sin(2 * math.pi * cutoff * distance) / (math.pi * distance)
        window = _bessel_i0(KAISER_BETA * math.sqrt(1.0 - ratio * ratio)) / denominator
        values.append(sinc * window)
    total = sum(values)
    return [value / total for value in values]


def _bessel_i0(x: float) -> float:
    total, term, order = 1.0, 1.0, 1
    while term > 1e-12 * total:
        term *= (x / (2 * order)) ** 2
        total += term
        order += 1
    return total


def _kernel_table(source_rate: int, target_rate: int, taps: int) -> tuple[list[list[float]], int, int]:
    """Kernels for every fractional position the conversion visits, plus the stepping constants."""
    divisor = gcd(source_rate, target_rate)
    step, period = source_rate // divisor, target_rate // divisor
    cutoff = CUTOFF * target_rate / source_rate
    phases = period if period <= MAX_PHASES else MAX_PHASES + 1
    scale = period if period <= MAX_PHASES else MAX_PHASES
    table = [lowpass_kernel(taps, cutoff, index / scale) for index in range(phases)]
    return table, step, period


def _lowpass(
    chunks: Iterable[list[float]], source_rate: int, target_rate: int
) -> Iterator[list[float]]:
    taps = tap_count(source_rate, target_rate)
    half = taps // 2
    table, step, period = _kernel_table(source_rate, target_rate, taps)
    exact = period <= MAX_PHASES
    buffer = [0.0] * (half - 1)  # silence before the first sample
    base = -(half - 1)  # absolute source index of buffer[0]
    numerator = 0  # output n sits at source position n * source_rate / target_rate
    phase = 0
    total = 0

    def emit(limit: int) -> list[float]:
        nonlocal numerator, phase, base
        block: list[float] = []
        while True:
            index = numerator // target_rate
            if index > limit:
                break
            start = index - half + 1 - base
            slot = phase if exact else (phase * MAX_PHASES + period // 2) // period
            block.append(_dot(buffer[start : start + taps], table[slot]))
            numerator += source_rate
            phase = (phase + step) % period
        drop = numerator // target_rate - half + 1 - base
        if drop > 0:
            del buffer[:drop]
            base += drop
        return block

    for chunk in chunks:
        buffer.extend(chunk)
        total += len(chunk)
        block = emit(base + len(buffer) - 1 - half)
        if block:
            yield block
    # Flush: pad the tail with silence, but keep the rule that an output needs a later sample.
    buffer.extend([0.0] * half)
    block = emit(total - 2)
    if block:
        yield block


def _linear(
    chunks: Iterable[list[float]], source_rate: int, target_rate: int
) -> Iterator[list[float]]:
    """Linear interpolation with exact integer positions; used when the rate goes up."""
    carry: float | None = None
    base = 0
    produced = 0
    for chunk in chunks:
        data = chunk if carry is None else [carry, *chunk]
        if not data:
            continue
        last = base + len(data) - 1
        block: list[float] = []
        while True:
            numerator = produced * source_rate
            index = numerator // target_rate
            if index + 1 > last:
                break
            fraction = (numerator % target_rate) / target_rate
            low = data[index - base]
            block.append(low + (data[index - base + 1] - low) * fraction)
            produced += 1
        carry = data[-1]
        base = last
        yield block
