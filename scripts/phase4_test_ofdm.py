"""Independent structural checks of the communication source."""
import unittest
import numpy as np
from phase4_ofdm import make_case,symbols,waveform,START,END,SIZE,CP


class SourceTests(unittest.TestCase):
    def test_constellation_cp_null_and_inverse(self):
        for modulation in ('qpsk','qam16'):
            c=make_case(95,modulation,210000,gain=6000)
            active,pilots,parts=symbols(c);floating,iq,details=waveform(c)
            self.assertEqual(details['complete_symbols'],6)
            self.assertEqual(details['cropped_symbols'],0)
            for j,(bins,time) in enumerate(parts):
                self.assertEqual(bins[0],0)
                self.assertEqual(np.count_nonzero(bins),len(active))
                np.testing.assert_allclose(np.fft.fft(time,norm='ortho'),bins,atol=2e-15)
                a=START+j*(SIZE+CP)
                np.testing.assert_array_equal(floating[a:a+CP],floating[a+SIZE:a+SIZE+CP])
                unpilot=np.delete(bins[active%SIZE],pilots)
                scale=np.sqrt(2 if modulation=='qpsk' else 10)
                allowed=(-1,1) if modulation=='qpsk' else (-3,-1,1,3)
                self.assertTrue(np.isin(np.rint(unpilot.real*scale).astype(int),allowed).all())
            self.assertFalse(np.any(iq[:START]));self.assertFalse(np.any(iq[END:]))
            self.assertLessEqual(np.max(np.abs(iq[:,0]-floating.real)),.5)
    def test_fixed_gain_determinism_and_variation(self):
        a=make_case(90,'qam16',210002,gain=6000)
        x=waveform(a)[1];np.testing.assert_array_equal(x,waveform(a)[1])
        b=dict(a,seed=210003);self.assertFalse(np.array_equal(x,waveform(b)[1]))
        a['signal']=dict(a['signal'],gain=32767)
        with self.assertRaisesRegex(ValueError,'overflow'):waveform(a)
    def test_frequency_translation(self):
        a=make_case(85,'qpsk',210004,gain=1)
        b=make_case(85,'qpsk',210004,gain=1,carrier_hz=1000000)
        x=waveform(a)[0];y=waveform(b)[0]
        np.testing.assert_allclose(y,x*np.exp(2j*np.pi*.01*np.arange(len(x))),atol=1e-11)
        self.assertTrue(make_case(95,'qpsk',210004,gain=1,carrier_hz=4000000)['crosses_nyquist'])


if __name__=='__main__':unittest.main(verbosity=2)
