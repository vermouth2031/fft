"""Generate IQ test files and SOFTWARE references for the implementation plan.

The spectral reference models input/window quantization and final FFT-output
quantization only. It does NOT model AMD FFT internal arithmetic or cycle timing.
Run: python -X utf8 tests/generate_iq_vectors.py
Dependencies: numpy; matplotlib is optional (for the reference figure).
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parents[1] / "data"
OUT = BASE / "vectors"
N, FS, LENGTH, SEED = 8192, 100_000_000, 32768, 20260915
TON, TOFF, KON, KOFF = 1_048_576, 262_144, 8, 32


def quantize(x):
    iq = np.column_stack((np.rint(x.real), np.rint(x.imag))).astype(np.int64)
    assert np.max(iq) <= 32767 and np.min(iq) >= -32768
    return iq.astype("<i2")


def rrc_taps(alpha, sps, span):
    t = np.arange(-span * sps // 2, span * sps // 2 + 1, dtype=float) / sps
    h = np.empty_like(t)
    for i, v in enumerate(t):
        if abs(v) < 1e-12:
            h[i] = 1 + alpha * (4 / np.pi - 1)
        elif abs(abs(v) - 1 / (4 * alpha)) < 1e-12:
            h[i] = alpha / np.sqrt(2) * ((1 + 2 / np.pi) * np.sin(np.pi / (4 * alpha)) + (1 - 2 / np.pi) * np.cos(np.pi / (4 * alpha)))
        else:
            h[i] = (np.sin(np.pi * v * (1 - alpha)) + 4 * alpha * v * np.cos(np.pi * v * (1 + alpha))) / (np.pi * v * (1 - (4 * alpha * v) ** 2))
    return h / np.sqrt(np.sum(h * h))


def qpsk_case(sps):
    rng = np.random.default_rng(SEED + sps)
    nsym = 24576 // sps
    symbols = ((2 * rng.integers(0, 2, nsym) - 1) + 1j * (2 * rng.integers(0, 2, nsym) - 1)) / np.sqrt(2)
    up = np.zeros(nsym * sps, dtype=complex)
    up[::sps] = symbols
    taps = rrc_taps(0.25, sps, 10)
    burst = np.convolve(up, taps, mode="full")
    burst *= 8192 / np.sqrt(np.mean(np.abs(burst) ** 2))
    start, end = 2048, 2048 + len(burst)
    x = np.zeros(LENGTH, dtype=complex)
    x[start:end] = burst
    x *= np.exp(2j * np.pi * 8_000_000 * np.arange(LENGTH) / FS)
    return quantize(x), {
        "kind": "RRC-QPSK", "sps": sps, "rolloff": 0.25,
        "rrc_span_symbols": 10, "rrc_taps": len(taps), "seed": SEED + sps,
        "carrier_offset_hz": 8_000_000, "symbol_rate_baud": FS / sps,
        "ideal_support_hz": 1.25 * FS / sps,
        "waveform_interval": [start, end],
        "interval_definition": "finite convolution array including filter transients and padded upsampling zeros",
    }


def burst_reference(iq):
    p = iq[:, 0].astype(np.int64) ** 2 + iq[:, 1].astype(np.int64) ** 2
    prefix = np.r_[np.int64(0), np.cumsum(p)]
    slide = prefix[1:] - prefix[np.maximum(0, np.arange(len(p)) - 15)]
    state, candidate, start, count, end = "idle", None, None, 0, None
    records = []
    for n, value in enumerate(slide):
        if state == "idle":
            if value > TON:
                candidate, count, state = n, 1, "start"
        elif state == "start":
            if value > TON:
                count += 1
                if count == KON:
                    start, state = candidate, "active"
            else:
                state = "idle"
        elif state == "active":
            if value < TOFF:
                end, count, state = n, 1, "end"
        else:
            if value < TOFF:
                count += 1
                if count == KOFF:
                    energy = int(prefix[end] - prefix[start])
                    peak_p = int(np.max(p[start:end]))
                    records.append({
                        "start": int(start), "end_exclusive": int(end),
                        "samples": int(end - start), "energy": energy,
                        "peak_uq16_16": math.isqrt(peak_p << 32),
                        "rms_uq16_16": math.isqrt((energy << 32) // (end - start)),
                        "complete": True,
                    })
                    state, start = "idle", None
            else:
                state = "active"
    if state in ("active", "end"):
        records.append({"start": int(start), "complete": False, "reason": "capture ended before a confirmed trailing gap"})
    return records


def spectrum_reference(iq, mode):
    n = np.arange(N)
    wcode = np.full(N, 2**17, dtype=np.int64) if mode == "rect" else np.rint((0.5 - 0.5 * np.cos(2 * np.pi * n / N)) * 2**17).astype(np.int64)
    # Products have <2**53 magnitude: conversion to float is exact for the integer
    # product and division by 512. np.rint implements ties-to-even here.
    prod = iq.astype(np.int64) * wcode[:, None]
    x24 = np.rint(prod.astype(np.float64) / 512).astype(np.int64)
    y = np.fft.fft(x24[:, 0] + 1j * x24[:, 1]) / (2**14)
    re, im = np.rint(y.real).astype(np.int64), np.rint(y.imag).astype(np.int64)
    assert np.max(re) < 2**23 and np.min(re) >= -(2**23)
    assert np.max(im) < 2**23 and np.min(im) >= -(2**23)
    p = np.fft.fftshift(re * re + im * im)
    total = int(np.sum(p, dtype=np.int64))
    if total == 0:
        return {"valid_power": False, "total_power": 0}, p
    cdf = np.cumsum(p, dtype=np.int64)
    lo = int(np.searchsorted(cdf, (total + 199) // 200))
    hi = int(np.searchsorted(cdf, total - total // 200))
    peak = int(np.argmax(p))
    return {
        "valid_power": True, "total_power": total,
        "q_peak": peak, "q_low": lo, "q_high": hi,
        "f_peak_hz": (peak - N // 2) * FS / N,
        "f_low_hz": (lo - N // 2) * FS / N,
        "f_high_hz": (hi - N // 2) * FS / N,
        "obw99_bin_center_hz": (hi - lo) * FS / N,
        "f_bandcenter_hz": (lo + hi - N) * FS / (2 * N),
        "resolution_limited": lo == hi,
    }, p


def make_cases():
    phase = np.array([1, 1j, -1, -1j], dtype=complex)
    tone = 8192 * phase[np.arange(LENGTH) % 4]
    x = np.zeros(LENGTH, dtype=complex)
    x[2048:26624] = tone[2048:26624]
    short = np.zeros(LENGTH, dtype=complex)
    short[7936:8448] = tone[7936:8448]
    q4, m4 = qpsk_case(4)
    q2, m2 = qpsk_case(2)
    return {
        "zero": (quantize(np.zeros(LENGTH, dtype=complex)), {"kind": "zero"}),
        "tone_pos_fs4": (quantize(tone), {"kind": "continuous complex tone", "frequency_hz": FS / 4, "amplitude_codes": 8192}),
        "tone_neg_fs4": (quantize(np.conj(tone)), {"kind": "continuous complex tone", "frequency_hz": -FS / 4, "amplitude_codes": 8192}),
        "burst_fs4": (quantize(x), {"kind": "rectangular-envelope tone burst", "waveform_interval": [2048, 26624], "true_samples": 24576}),
        "qpsk_sps4": (q4, m4),
        "qpsk_sps2": (q2, m2),
        "short512_boundary": (quantize(short), {"kind": "short tone burst at FFT boundary", "waveform_interval": [7936, 8448], "true_samples": 512}),
        "negative_fullscale_dc": (np.full((LENGTH, 2), -32768, dtype="<i2"), {"kind": "both IQ components at negative fullscale"}),
    }


def plot_examples(cases):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    plt.rcParams.update({"font.size": 11, "axes.grid": True, "grid.alpha": 0.22})
    fig, ax = plt.subplots(2, 2, figsize=(13, 8.4), constrained_layout=True)
    f = (np.arange(N) - N // 2) * FS / N / 1e6
    _, p = spectrum_reference(cases["tone_pos_fs4"][0][:N], "rect")
    ax[0, 0].plot(f, 10 * np.log10(np.maximum(p / p.max(), 1e-12)), color="#1665b0")
    ax[0, 0].set(title="1. Complex tone: +25 MHz", xlabel="Baseband frequency (MHz)", ylabel="Power / peak (dB)", ylim=(-125, 5))
    iq = cases["burst_fs4"][0].astype(np.float64)
    ax[0, 1].plot(np.arange(LENGTH) / FS * 1e6, np.hypot(iq[:, 0], iq[:, 1]), color="#137c65")
    ax[0, 1].set(title="2. Tone burst: 24,576 samples = 245.76 us", xlabel="Time (us)", ylabel="Raw IQ envelope (codes)")
    for name, label, color in (("qpsk_sps4", "sps=4; support 31.25 MHz", "#1665b0"), ("qpsk_sps2", "sps=2; support 62.5 MHz", "#de782b")):
        _, p = spectrum_reference(cases[name][0][N:2*N], "hann")
        ax[1, 0].plot(f, 10 * np.log10(np.maximum(p / p.max(), 1e-8)), label=label, color=color, alpha=0.8, linewidth=0.9)
    ax[1, 0].set(title="3. RRC-QPSK: changing the actual signal bandwidth", xlabel="Baseband frequency (MHz)", ylabel="Power / each peak (dB)", ylim=(-80, 5))
    ax[1, 0].legend(fontsize=9)
    _, pr = spectrum_reference(cases["short512_boundary"][0][:N], "rect")
    _, ph = spectrum_reference(cases["short512_boundary"][0][:N], "hann")
    for p, label, color in ((pr, "Rectangular", "#1665b0"), (ph, "Hann", "#b34358")):
        ax[1, 1].plot(f, 10 * np.log10(np.maximum(p / pr.max(), 1e-12)), label=label, color=color, linewidth=0.9)
    ax[1, 1].set(title="4. Short burst near a window edge", xlabel="Baseband frequency (MHz)", ylabel="Power / rectangular peak (dB)", xlim=(23, 27), ylim=(-100, 5))
    ax[1, 1].legend()
    fig.suptitle("Software references at Fs = 100 MSPS | Not FPGA measurements", fontsize=16, fontweight="bold")
    path = BASE / "software_reference_examples.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path.name


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    hann_codes = np.rint((0.5 - 0.5 * np.cos(2 * np.pi * np.arange(N) / N)) * 2**17).astype(np.int64)
    assert hann_codes[0] == 0 and hann_codes[N // 2] == 131072
    (OUT / "hann_u18_f17.mem").write_text("".join(f"{int(v):05x}\n" for v in hann_codes), encoding="ascii")
    cases = make_cases()
    manifest = {
        "reference_scope": "Software reference: exact integer time metrics; FFT input/window quantization and output-only rounding. NOT AMD bit-accurate FFT, RTL simulation, or FPGA measurement.",
        "sample_rate_hz": FS, "fft_length": N, "record_samples": LENGTH,
        "hann_rom": "hann_u18_f17.mem",
        "packing": "little-endian signed int16 I then signed int16 Q; mem word[15:0]=I, word[31:16]=Q",
        "detector": {"moving_sum_length": 16, "Ton": TON, "Toff": TOFF, "Kon": KON, "Koff": KOFF, "start_comparison": ">", "end_comparison": "<"},
        "cases": {},
    }
    for name, (iq, metadata) in cases.items():
        binary, memory = OUT / f"{name}.bin", OUT / f"{name}.mem"
        binary.write_bytes(iq.tobytes(order="C"))
        unsigned = iq.astype(np.int64) & 0xffff
        words = unsigned[:, 0] | (unsigned[:, 1] << 16)
        memory.write_text("".join(f"{int(v):08x}\n" for v in words), encoding="ascii")
        assert np.array_equal(np.frombuffer(binary.read_bytes(), dtype="<i2").reshape(-1, 2), iq)
        parsed = np.array([int(line, 16) for line in memory.read_text().splitlines()], dtype="<u4")
        assert parsed.tobytes() == binary.read_bytes()
        windows = []
        for wid in range(LENGTH // N):
            frame = iq[wid*N:(wid+1)*N]
            p = frame[:, 0].astype(np.int64)**2 + frame[:, 1].astype(np.int64)**2
            energy, peak = int(np.sum(p)), int(np.max(p))
            record = {"window_id": wid, "first_sample": wid*N, "energy": energy,
                      "peak_uq16_16": math.isqrt(peak << 32),
                      "rms_uq16_16": math.isqrt(energy << 19)}
            for mode in ("rect", "hann"):
                record[mode] = spectrum_reference(frame, mode)[0]
            windows.append(record)
        manifest["cases"][name] = {
            "metadata": metadata, "binary": binary.name, "mem": memory.name,
            "sha256_bin": hashlib.sha256(binary.read_bytes()).hexdigest(),
            "max_abs_component": int(np.abs(iq.astype(np.int64)).max()),
            "bursts": burst_reference(iq), "windows": windows,
        }
    tone = manifest["cases"]["tone_pos_fs4"]["windows"][0]
    assert tone["rect"]["q_peak"] == 6144
    assert tone["rect"]["f_peak_hz"] == 25_000_000
    assert tone["rect"]["obw99_bin_center_hz"] == 0
    assert tone["peak_uq16_16"] == tone["rms_uq16_16"] == 8192 * 65536
    assert manifest["cases"]["tone_neg_fs4"]["windows"][0]["rect"]["q_peak"] == 2048
    assert manifest["cases"]["negative_fullscale_dc"]["windows"][0]["energy"] == 2**44
    burst = manifest["cases"]["burst_fs4"]["bursts"][0]
    assert burst["start"] == 2048 and burst["end_exclusive"] == 26639
    assert burst["samples"] == 24591  # 15-sample smoothing tail, not a code bug.
    assert manifest["cases"]["zero"]["bursts"] == []
    manifest["figure"] = plot_examples(cases)
    (OUT / "reference_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"cases": len(cases), "samples_per_case": LENGTH, "frequency_results": len(cases) * (LENGTH//N) * 2,
        "packing_and_analytic_checks": "passed", "figure": manifest["figure"],
        "tone_burst_detected_samples": burst["samples"],
        "qpsk_sps4_window1_hann": manifest["cases"]["qpsk_sps4"]["windows"][1]["hann"],
        "qpsk_sps2_window1_hann": manifest["cases"]["qpsk_sps2"]["windows"][1]["hann"]}, indent=2))


if __name__ == "__main__":
    main()
