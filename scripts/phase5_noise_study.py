"""Bounded offline exposure study; run intervals retain state across chunks.

Raw I16/Q16 streams are saved. This is not a continuous physical-board test.
Only interval/flag decisions are studied here; amplitude arithmetic is unchanged.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from threshold_reference import reference_threshold, runs


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def thresholds(iq):
    p = iq[:1024].astype(np.int64)
    mean = float(np.mean(p[:, 0] ** 2 + p[:, 1] ** 2))
    return max(2, math.ceil(48 * mean)), max(1, math.ceil(28 * mean))


class StreamIntervals:
    """Run-based oracle, using absolute indices and persistent 16-sample history."""
    def __init__(self, ton, toff, maximum=1048576):
        self.ton, self.toff, self.maximum = ton, toff, maximum
        self.history = np.zeros(15, dtype=np.int64)
        self.position = self.cursor = 0
        self.on_tail = self.off_tail = self.start = None
        self.records = []

    def feed(self, iq):
        x = iq.astype(np.int64)
        power = x[:, 0] ** 2 + x[:, 1] ** 2
        extended = np.r_[self.history, power]
        prefix = np.r_[np.int64(0), np.cumsum(extended)]
        sliding = prefix[16:] - prefix[:-16]
        self.history = extended[-15:].copy()
        end = self.position + len(power)
        intervals = []
        for mask, attr in ((sliding > self.ton, 'on_tail'), (sliding < self.toff, 'off_tail')):
            found = [(a + self.position, b + self.position) for a, b in runs(mask)]
            tail = getattr(self, attr)
            if found and found[0][0] == self.position and tail is not None:
                found[0] = (tail, found[0][1])
            setattr(self, attr, found[-1][0] if found and found[-1][1] == end else None)
            intervals.append(found)
        on, off = intervals
        oi = fi = 0
        while True:
            if self.start is None:
                while oi < len(on):
                    a, b = on[oi]
                    a = max(a, self.cursor)
                    if b - a >= 16:
                        self.start = a
                        break
                    oi += 1
                if self.start is None:
                    break
            start = self.start
            timeout = start + self.maximum
            ending = None
            while fi < len(off):
                a, b = off[fi]
                a = max(a, start + 16)
                if b - a >= 8:
                    ending = a
                    break
                fi += 1
            # END_CAND confirmation wins when it coincides with timeout.
            if ending is not None and ending + 8 <= timeout:
                self.records.append((start, ending, 0))
                self.cursor, self.start = ending + 8, None
            elif timeout <= end:
                self.records.append((start, timeout, 1024))
                self.cursor, self.start = timeout, None
            else:
                break
        self.position = end

    def finish(self):
        if self.start is not None:
            self.records.append((self.start, self.position, 256))
            self.start = None
        return self.records


def self_test():
    # Independent existing finite oracle, irregular seams through confirmations.
    for seed in range(310500, 310540):
        rng = np.random.default_rng(seed)
        iq = np.rint(rng.normal(0, 256, (12000, 2))).astype('<i2')
        for a, b in ((13, 110), (777, 3100), (9100, 12000)):
            iq[a:b, 0] += 4096
        ton, toff = thresholds(iq[:12].repeat(100, axis=0))
        detector = dict(mode='threshold', ton=ton, toff=toff, kon=16, koff=8,
                        gap_min=32, max_burst_samples=1048576)
        expected = [(r['start_sample'], r['end_sample'], r['flags'])
                    for r in reference_threshold(iq, detector)]
        for chunk in (1, 7, 31, 1024, 12000):
            model = StreamIntervals(ton, toff)
            for offset in range(0, len(iq), chunk):
                model.feed(iq[offset:offset + chunk])
            assert model.finish() == expected, (seed, chunk, model.records, expected)
    iq = np.full((1048576 + 64, 2), 100, dtype='<i2')
    model = StreamIntervals(1, 0)
    for offset in range(0, len(iq), 32768):
        model.feed(iq[offset:offset + 32768])
    assert model.finish() == [(0, 1048576, 1024), (1048576, len(iq), 256)]
    return dict(finite_comparisons=200, timeout_cases=1, status='PASS')


def profile_iq(rng, count, std, profile, offset, total):
    n = np.arange(offset, offset + count)
    if profile.startswith('ramp'):
        db = float(profile.split('_')[1])
        scale = std * 10 ** (db * n / (total - 1) / 20)
    elif profile == 'step_6':
        scale = np.where(n < total // 2, std, std * 10 ** (6 / 20))
    else:
        scale = std
    iq = rng.standard_normal((count, 2)) * (scale[:, None] if np.ndim(scale) else scale)
    if profile == 'impulse_dc':
        iq[n >= total // 2, 0] += 2 * std
        iq[(n >= total // 4) & (n < total // 4 + 128), 0] += 4 * std
    rounded = np.rint(iq)
    clipped = int(np.count_nonzero((rounded < -32768) | (rounded > 32767)))
    return np.clip(rounded, -32768, 32767).astype('<i2'), clipped


def study(out, seconds):
    out.mkdir(parents=True, exist_ok=False)
    checks = self_test()
    benchmark_start = time.monotonic()
    rng = np.random.default_rng(310599)
    benchmark_iq, _ = profile_iq(rng, 1048576, 1024, 'stationary', 0, 1048576)
    model = StreamIntervals(*thresholds(benchmark_iq))
    model.feed(benchmark_iq)
    benchmark = dict(samples=1048576, elapsed_seconds=time.monotonic() - benchmark_start)
    spec = dict(scope='OFFLINE ONLY; unique saved quantized noise, not board RAM replay',
                sample_rate_hz=100000000, seconds_per_stationary_layer=seconds,
                component_std_codes=[256, 1024, 4096], stationary_seeds=[311100, 311101, 311102],
                nonstationary_profiles=['ramp_-6', 'ramp_-3', 'ramp_3', 'ramp_6', 'step_6', 'impulse_dc'],
                nonstationary_seeds=list(range(311200, 311218)), nonstationary_samples=1048576,
                detector=dict(on_multiple=3, off_multiple=1.75, kon=16, koff=8,
                              calibration_samples=1024, max_burst_samples=1048576),
                finite_block_samples=32768, stream_chunk_samples=1048576,
                stationary_effective_samples=math.ceil(seconds * 100000000),
                nonstationary_truth='No wanted signal; all reported intervals are false detections',
                clipping='Quantize and saturate to I16/Q16; count clipped components without seed rejection',
                source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                self_test=checks, benchmark=benchmark)
    save(out / 'specification.json', spec)
    print('NOISE_BENCHMARK', benchmark, flush=True)
    results = []
    for layer, std in enumerate(spec['component_std_codes']):
        profiles = ['stationary'] + spec['nonstationary_profiles']
        for pi, profile in enumerate(profiles):
            total = spec['stationary_effective_samples'] + 1024 if pi == 0 else 1048576
            seed = 311100 + layer if pi == 0 else 311200 + layer * 6 + pi - 1
            rng = np.random.default_rng(seed)
            stream = None
            finite_events = finite_effective = clipped = 0
            digest = hashlib.sha256()
            path = out / f'std{std}_{profile}_s{seed}.bin'
            with path.open('xb') as raw:
                for offset in range(0, total, 1048576):
                    iq, nc = profile_iq(rng, min(1048576, total - offset), std, profile, offset, total)
                    clipped += nc
                    payload = iq.tobytes(); raw.write(payload); digest.update(payload)
                    if stream is None:
                        stream = StreamIntervals(*thresholds(iq))
                    stream.feed(iq)
                    if pi == 0:
                        for begin in range(0, len(iq), 32768):
                            block = iq[begin:begin + 32768]
                            if len(block) <= 1024:
                                continue
                            finite = StreamIntervals(*thresholds(block))
                            finite.feed(block)
                            finite_events += sum(a >= 1024 for a, b, flags in finite.finish())
                            finite_effective += len(block) - 1024
            records = stream.finish()
            post = [r for r in records if r[0] >= 1024]
            exposure = (total - 1024) / 100000000
            result = dict(std=std, profile=profile, seed=seed, raw=str(path), sha256=digest.hexdigest(),
                          samples=total, clipped_components=clipped, fixed_ton=stream.ton, fixed_toff=stream.toff,
                          continuous_records=records, continuous_post_calibration_events=len(post),
                          continuous_effective_seconds=exposure,
                          continuous_zero_event_poisson95_upper_per_second=(
                              -math.log(.05) / exposure if not post and pi == 0 else None))
            if pi == 0:
                result.update(finite_post_calibration_events=finite_events,
                              finite_effective_seconds=finite_effective / 100000000,
                              finite_zero_event_poisson95_upper_per_second=(
                                  -math.log(.05) / (finite_effective / 100000000) if not finite_events else None))
            results.append(result)
            save(out / 'progress.json', results)
            print('NOISE_CASE_COMPLETE', std, profile, len(post), 'clipped', clipped, flush=True)
    report = dict(status='COMPLETE', self_test=checks, cases=results,
                  specification_sha256=hashlib.sha256((out / 'specification.json').read_bytes()).hexdigest(),
                  limitations=['Offline interval model, not real-board throughput evidence',
                               'Overlapping sliding windows correlate; Poisson bounds are conditional',
                               'Finite and continuous analyses share input, not independent trials',
                               'No threshold retuning on holdout; nonstationary detections remain failures'])
    save(out / 'study.json', report)
    save(ROOT / 'reports/phase5_noise_validation.json', report)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--seconds', type=float, default=3)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        print(self_test())
    else:
        if args.seconds <= 0:
            parser.error('--seconds must be positive')
        study(args.out.resolve(), args.seconds)
