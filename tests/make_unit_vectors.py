from pathlib import Path
import math,random
r=random.Random(20260916);root=Path(__file__).resolve().parents[1];out=root/'data'
values=[0,1,2,3,4,2**31,2**32-1,2**44,2**63,2**64-1]+[r.getrandbits(64) for _ in range(246)]
rows=[]
for i,n in enumerate(values):
 d=[1,2,200,8192,24591,1048576,2**32-1,2**63,2**64-1][i%9] if i<32 else max(1,r.getrandbits(64))
 rows.append(f'{n:016x}{d:016x}{n//d:016x}{n%d:016x}{math.isqrt(n):08x}\n')
(out/'math_vectors.mem').write_text(''.join(rows),encoding='ascii')
print('Generated 256 exact divider/square-root vectors')
