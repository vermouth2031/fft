"""Native Python integer references for the narrowed exact math datapaths."""
import math
import random
from pathlib import Path

root = Path(__file__).resolve().parents[1]
rng = random.Random(312031)
values = {0, 1, 2, 3, (1 << 64) - 1}
for bits in range(1, 33):
    for q in ((1 << bits) - 1, 1 << (bits - 1)):
        for offset in (-1, 0, 1, 2*q):
            x = q*q + offset
            if 0 <= x < 1 << 64:
                values.add(x)
values.update(rng.getrandbits(64) for _ in range(10000))
divisors = [0, 1, 2, 3, 200, 16384, 1048576, (1 << 32)-1, 1 << 63, (1 << 64)-1]
rows = []
for index, num in enumerate(sorted(values)):
    den = divisors[index % len(divisors)] if index % 2 == 0 else rng.getrandbits(64)
    quotient, remainder = divmod(num, den) if den else (0, 0)
    rows.append(f'{num:016x}{den:016x}{quotient:016x}{remainder:016x}{math.isqrt(num):08x}\n')
(root/'data/phase12_math_ranges.mem').write_text(''.join(rows), encoding='ascii')
assert len(rows) == 10220
print('PHASE12_MATH_REFERENCE_PASS', len(rows))
