import unittest
import numpy as np
from phase9_ofdm import symbols,waveform


class OFDMTests(unittest.TestCase):
    def test_full_band_constellation_cp_and_determinism(self):
        for modulation in ('qpsk','qam16'):
            spec=dict(ifft_length=8192,cyclic_prefix=512,active_half=4095,modulation=modulation,gain=6000)
            active,parts=symbols(spec,212100,3)
            self.assertEqual(len(active),8190)
            for bins,x in parts:
                self.assertEqual(bins[0],0);self.assertEqual(bins[4096],0)
                self.assertEqual(np.count_nonzero(bins),8190)
                np.testing.assert_array_equal(x[:512],x[8192:])
                np.testing.assert_allclose(np.fft.fft(x[512:]/6000,norm='ortho'),bins,atol=1e-12)
                self.assertLess(max(abs(x.real).max(),abs(x.imag).max()),32767)
            x=waveform(spec,212100,26112)
            np.testing.assert_array_equal(x,waveform(spec,212100,26112))
            self.assertFalse(np.array_equal(x,waveform(spec,212101,26112)))
            with self.assertRaises(ValueError):waveform(spec,212100,26111)


if __name__=='__main__':unittest.main()
