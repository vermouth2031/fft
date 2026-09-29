"""Explicit-lifetime AMD oracle. Import performs no extraction or generation.

Natural-order outputs match the RTL indexed bit-reversed stream after reordering.
NumPy FFT is never substituted for AMD fixed-point arithmetic.
"""
from __future__ import annotations
import ctypes as C
import hashlib
import math
import os
import sys
from pathlib import Path
import zipfile
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'host'))
from build_rates import SAMPLE_RATE_HZ
N, FS = 8192, SAMPLE_RATE_HZ
SCALE = (3, 2, 2, 2, 2, 2, 1)


class Generics(C.Structure):
    _fields_ = [(k, C.c_int) for k in ('nfft', 'arch', 'has_nfft', 'float', 'width',
                'twiddle', 'scaled', 'bfp', 'round', 'ssr', 'inverse')]


DP, IP = C.POINTER(C.c_double), C.POINTER(C.c_int)


class Inputs(C.Structure):
    _fields_ = [('nfft', C.c_int), ('re', DP), ('re_size', C.c_int), ('im', DP),
                ('im_size', C.c_int), ('scale', IP), ('scale_size', C.c_int), ('direction', C.c_int)]


class Outputs(C.Structure):
    _fields_ = [('re', DP), ('re_size', C.c_int), ('im', DP), ('im_size', C.c_int),
                ('exponent', C.c_int), ('overflow', C.c_int)]


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def signed_round(value, divisor):
    return (1 if value >= 0 else -1) * ((abs(value) + divisor // 2) // divisor)


def hz(q):
    return signed_round((q - N // 2) * FS, N)


def checked_iq(iq):
    values = np.asarray(iq)
    if values.shape != (N, 2) or values.dtype.kind not in 'iu':
        raise ValueError('Reference requires exactly 8192 integer I/Q pairs')
    if np.any(values < -32768) or np.any(values > 32767):
        raise ValueError('I/Q outside int16 range; clipping is not permitted')
    return values.astype(np.int64)


class FFTReference:
    def __init__(self, *, sample_rate_hz=FS, vivado=None, model_dir=None, hann_path=None):
        if sample_rate_hz != FS:
            raise ValueError('Reference rate must match the selected build profile')
        self.state = None
        self.dll_dir = None
        vivado = Path(vivado or os.environ.get('VIVADO_ROOT', r'D:\VivadoMM\2026.1\Vivado'))
        archive = vivado / 'data/ip/xilinx/xfft_v9_1/cmodel/xfft_v9_1_bitacc_cmodel_nt64.zip'
        archive_hash = digest(archive)
        model_dir = Path(model_dir or ROOT / 'build/cmodel_reference' / archive_hash[:16])
        model_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as source:
            for member in source.infolist():
                target = (model_dir / member.filename).resolve()
                if not target.is_relative_to(model_dir.resolve()):
                    raise ValueError('Unsafe C model archive member')
                if not target.exists():
                    source.extract(member, model_dir)
                elif not member.is_dir() and target.read_bytes() != source.read(member):
                    raise ValueError('Extracted C model differs from vendor archive')
        hann_path = Path(hann_path or ROOT / 'data/vectors/hann_u18_f17.mem')
        self.hann = np.array([int(s, 16) for s in hann_path.read_text().splitlines()], dtype=np.int64)
        if self.hann.shape != (N,) or np.any(self.hann < 0) or np.any(self.hann > 131072):
            raise ValueError('Invalid Hann coefficients')
        dll = model_dir / 'libIp_xfft_v9_1_bitacc_cmodel.dll'
        self.identity = dict(oracle='AMD xfft v9.1 bit-accurate C model', nfft=13,
            sample_rate_hz=FS, input_width=24, twiddle_width=18, scaling_schedule=list(SCALE),
            rounding='convergent', archive_sha256=archive_hash, dll_sha256=digest(dll),
            archive_path=str(archive.resolve()), dll_path=str(dll.resolve()),
            hann_sha256=digest(hann_path), interface_sha256=digest(__file__))
        try:
            self.dll_dir = os.add_dll_directory(str(model_dir.resolve()))
            self.lib = C.CDLL(str(dll.resolve()))
            self.create = self.lib.xilinx_ip_xfft_v9_1_create_state
            self.create.argtypes, self.create.restype = [Generics], C.c_void_p
            self.destroy = self.lib.xilinx_ip_xfft_v9_1_destroy_state
            self.destroy.argtypes, self.destroy.restype = [C.c_void_p], None
            self.simulate = self.lib.xilinx_ip_xfft_v9_1_bitacc_simulate
            self.simulate.argtypes = [C.c_void_p, Inputs, C.POINTER(Outputs)]
            self.simulate.restype = C.c_int
            self.state = self.create(Generics(13, 3, 0, 0, 24, 18, 1, 0, 1, 1, 0))
            if not self.state:
                raise RuntimeError('AMD C model initialization failed')
            self.scale = (C.c_int * 7)(*SCALE)
        except Exception:
            self.close()
            raise

    def close(self):
        if self.state:
            self.destroy(self.state)
            self.state = None
        if self.dll_dir:
            self.dll_dir.close()
            self.dll_dir = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def window(self, iq, mode='rect', window_id=0):
        if not self.state:
            raise RuntimeError('Reference model is closed')
        if mode not in ('rect', 'hann'):
            raise ValueError('Window must be rect or hann')
        raw = checked_iq(iq)
        coeff = self.hann if mode == 'hann' else np.full(N, 131072, dtype=np.int64)
        # Product <= 2**32; power-of-two division is exact in float64.
        x = np.rint(raw * coeff[:, None] / 512).astype(np.int64)
        re = np.ascontiguousarray(x[:, 0] / 2**23, dtype=np.float64)
        im = np.ascontiguousarray(x[:, 1] / 2**23, dtype=np.float64)
        yr, yi = np.zeros(N), np.zeros(N)
        inp = Inputs(13, re.ctypes.data_as(DP), N, im.ctypes.data_as(DP), N, self.scale, 7, 1)
        out = Outputs(yr.ctypes.data_as(DP), N, yi.ctypes.data_as(DP), N, 0, 0)
        code = self.simulate(self.state, inp, C.byref(out))
        if code or out.overflow:
            raise ValueError(f'AMD FFT failure: return={code}, overflow={out.overflow}')
        ir, ii = np.rint(yr * 2**23).astype(np.int64), np.rint(yi * 2**23).astype(np.int64)
        packed = (ir & 0xffffff) | ((ii & 0xffffff) << 24)
        power = np.fft.fftshift(ir * ir + ii * ii)
        total, peak = int(power.sum()), int(np.argmax(power))
        lo = hi = 0
        if total:
            cumulative = np.cumsum(power)
            lo = int(np.searchsorted(cumulative, (total + 199) // 200))
            hi = int(np.searchsorted(cumulative, total - total // 200))
        time_power = raw[:, 0] ** 2 + raw[:, 1] ** 2
        energy, pp = int(time_power.sum()), int(time_power.max())
        result = dict(window_id=window_id, total=total, peak_power=int(power.max()),
            q_peak=peak, q_low=lo, q_high=hi, f_peak_hz=hz(peak) if total else 0,
            f_low_hz=hz(lo) if total else 0, f_high_hz=hz(hi) if total else 0,
            bandwidth_hz=((hi-lo)*FS+N//2)//N if total else 0,
            center_hz=signed_round((lo+hi-N)*FS, 2*N) if total else 0,
            energy=energy, peak_uq16_16=math.isqrt(pp << 32), rms_uq16_16=math.isqrt(energy << 19))
        return result, packed, power.reshape(1024, 8).max(axis=1)
