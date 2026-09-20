"""Create deterministic directed/random fixtures for the digital frame RTL."""
import argparse
import json
import random
import struct
from pathlib import Path

from frame_length_reference import reference_digital_zero

ROOT = Path(__file__).resolve().parents[1]


def build_cases():
    cases = []

    def add(name, values, gap=32, maximum=1048576, simultaneous_finish=False):
        cases.append(dict(name=name, values=values, gap=gap, maximum=maximum,
                          simultaneous_finish=simultaneous_finish))

    zero = (0, 0)
    for length in (1, 2, 15, 16, 17, 64, 512, 4096, 24576):
        for amplitude in ((1, 0), (0, 1), (8192, -8192), (-32768, -32768)):
            add(f"length_{length}_amplitude_{amplitude}",
                [zero] * 32 + [amplitude] * length + [zero] * 32,
                simultaneous_finish=length % 2 == 1)
    for gap in (1, 16, 32, 65535):
        for interior in (gap - 1, gap, gap + 1):
            add(f"gap_{gap}_interior_{interior}",
                [zero] * gap + [(3, 4)] * 2 + [zero] * interior +
                [(-3, -4)] * 3 + [zero] * gap, gap=gap)
    for gap in (1, 16, 32):
        for suffix in (0, gap - 1, gap, gap + 1):
            add(f"finish_gap_{gap}_suffix_{suffix}",
                [(3, 4)] * 5 + [zero] * suffix, gap=gap,
                simultaneous_finish=suffix % 2 == 0)
    for maximum in (1, 2, 3, 8, 16, 17, 32, 33):
        for gap in (1, 4, 32):
            add(f"split_max_{maximum}_gap_{gap}",
                [zero] * gap + [(3, 4)] * 34 + [zero] * (gap - 1) +
                [(0, -32768)] * 33 + [zero] * gap,
                gap=gap, maximum=maximum, simultaneous_finish=True)
        add(f"split_at_finish_max_{maximum}", [(1, -1)] * (maximum * 3),
            maximum=maximum, simultaneous_finish=True)
    add("all_zero", [zero] * 8192)
    add("unconfirmed_leading_short_zero", [zero] * 3 + [(1, 0)] * 5 + [zero] * 32)
    add("acquisition_start_nonzero", [(1, 1)] * 31 + [zero] * 32)
    add("cross_fft_boundary", [zero] * 8190 + [(3, 4)] * 64 + [zero] * 32)
    add("cross_replay_boundary", [zero] * 32760 + [(3, 4)] * 64 + [zero] * 32)
    rng = random.Random(20260918)
    for n in range(100):
        gap = rng.choice((1, 2, 3, 8, 16, 32))
        values = [zero if rng.randrange(5) < 3 else
                  (rng.randrange(-32768, 32768), rng.randrange(-32768, 32768))
                  for _ in range(rng.randrange(1, 200))]
        add(f"random_{n:03}", values, gap=gap,
            maximum=rng.choice((1, 2, 3, 8, 32, 1048576)),
            simultaneous_finish=bool(n % 2))
    for name in ("burst_fs4", "qpsk_sps2", "qpsk_sps4"):
        source = ROOT / "data" / "vectors" / f"{name}.bin"
        if source.exists():
            values = list(struct.iter_unpack("<hh", source.read_bytes()))
            add(name, values)
    return cases


def generate(out):
    out.mkdir(parents=True, exist_ok=True)
    cases = build_cases()
    summary = []
    with (out / "digital_cases.txt").open("w", encoding="ascii") as stream:
        stream.write(f"{len(cases)}\n")
        for case in cases:
            values = case["values"]
            expected = reference_digital_zero([i for i, _ in values],
                                              [q for _, q in values],
                                              gap_min=case["gap"], max_burst=case["maximum"])
            stream.write(f"{len(values)} {case['gap']} {case['maximum']} "
                         f"{len(expected)} {int(case['simultaneous_finish'])}\n")
            for burst_id, record in enumerate(expected):
                packed = (record["flags"] << 256 | burst_id << 224 |
                          record["start_sample"] << 160 | record["end_sample"] << 96 |
                          record["energy"] << 32 | record["peak_power"])
                stream.write(f"{packed:072x}\n")
            for i, q in values:
                stream.write(f"{((q & 65535) << 16) | (i & 65535):08x}\n")
            summary.append(dict(name=case["name"], samples=len(values),
                                gap_min=case["gap"], max_burst=case["maximum"],
                                bursts=len(expected), simultaneous_finish=case["simultaneous_finish"]))
    (out / "cases.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"DIGITAL_FIXTURES cases={len(cases)} samples={sum(c['samples'] for c in summary)} "
          f"bursts={sum(c['bursts'] for c in summary)} out={out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "build" / "digital_burst_vectors")
    generate(parser.parse_args().out)
