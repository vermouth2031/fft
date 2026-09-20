"""Independent interval model for quantized I/Q with an exact zero background.

This groups nonzero sample indices first, then segments each observed interval;
it deliberately does not emulate the clocked RTL state machine. A timeout is an
observed segment, not a confirmed waveform end. Confirmation zeros can therefore
appear in timeout segments when max_burst is smaller than the confirmation gap.
"""
from math import isqrt

DIGITAL_ZERO = 1 << 12
START_UNCONFIRMED = 1 << 13
CAPTURE_TRUNCATED = 1 << 8
DETECTOR_TIMEOUT = 1 << 10


def reference_digital_zero(samples_i, samples_q, gap_min=32, start_index=0,
                           max_burst=1048576, finish=True):
    """Return measured intervals, integer amplitudes, and explicit status flags.

    ``peak_q16`` and ``rms_q16`` match the existing hardware Q16.16 records.
    ``peak`` and ``rms`` are those same quantized values in ADC-code units.
    START_UNCONFIRMED means fewer than gap_min preceding observed zeros, or a
    continuation after a forced split. ``finish=False`` leaves an open suffix
    unreported except for timeout segments already emitted.
    """
    if len(samples_i) != len(samples_q):
        raise ValueError("I and Q lengths differ")
    if not 1 <= gap_min <= 65535:
        raise ValueError("gap_min must be in 1..65535")
    if not 1 <= max_burst <= 1048576:
        raise ValueError("max_burst must be in 1..1048576")
    if start_index < 0:
        raise ValueError("start_index must be nonnegative")
    power = []
    for i, q in zip(samples_i, samples_q):
        i, q = int(i), int(q)
        if not -32768 <= i <= 32767 or not -32768 <= q <= 32767:
            raise ValueError("I/Q must be signed 16-bit integers")
        power.append(i * i + q * q)
    nonzero = [n for n, p in enumerate(power) if p]
    if not nonzero:
        return []
    groups = []
    first = previous = nonzero[0]
    for n in nonzero[1:]:
        if n - previous - 1 >= gap_min:
            groups.append((first, previous))
            first = n
        previous = n
    groups.append((first, previous))
    records = []

    def append(first, end, flags):
        values = power[first:end]
        energy = sum(values)
        maximum = max(values, default=0)
        count = end - first
        peak_q16 = isqrt(maximum << 32)
        rms_q16 = isqrt((energy << 32) // count)
        records.append(dict(start_sample=first + start_index,
                            end_sample=end + start_index,
                            length_samples=count, energy=energy,
                            peak_power=maximum, peak_q16=peak_q16,
                            rms_q16=rms_q16, peak=peak_q16 / 65536,
                            rms=rms_q16 / 65536, flags=flags))

    for group_no, (first, last) in enumerate(groups):
        confirmed = len(power) - last - 1 >= gap_min
        observation_end = last + 1 + gap_min if confirmed else len(power)
        flags = DIGITAL_ZERO
        if group_no == 0 and first < gap_min:
            flags |= START_UNCONFIRMED
        segment = first
        # Confirmation on the exact size-limit sample takes precedence.
        while (segment + max_burst < observation_end if confirmed else
               segment + max_burst <= observation_end):
            append(segment, segment + max_burst, flags | DETECTOR_TIMEOUT)
            segment += max_burst
            flags |= START_UNCONFIRMED
        if confirmed and segment <= last:
            append(segment, last + 1, flags)
        elif not confirmed and finish and segment < observation_end:
            append(segment, observation_end, flags | CAPTURE_TRUNCATED)
    return records
