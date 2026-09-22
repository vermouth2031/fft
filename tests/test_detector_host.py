"""Detector negotiation, provenance and length semantics without a physical board."""
import contextlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'host'))
import iq_client as h


def burst_record(start=4,end=7,flags=1<<12,rate=100000000):
    w=[0]*16
    w[0]=0x42525331;w[1]=flags;w[5]=rate
    w[6]=start;w[8]=end;w[10]=end-start
    w[11]=65536;w[12]=65536;w[13]=end-start
    return struct.pack('<16I',*w)


class DetectorHostTests(unittest.TestCase):
    def fake_client(self,version=0x10001,capabilities=1,rate=100000000):
        c=h.Client.__new__(h.Client);c.requests=[]
        def read(offset,count=1):
            if offset==0x84:return tuple(c.requests[-1][1][-2:])
            return ({4:version,0x8c:capabilities,0x10:rate,0x14:125000000}[offset],)
        c.read=read;c.request=lambda *args:c.requests.append(args)
        return c

    def test_legacy_threshold_uses_thirteen_words(self):
        c=self.fake_client(version=0x10000)
        c.configure(list(range(13)))
        self.assertEqual(c.requests,[(4,list(range(13)))])

    def test_new_configuration_explicitly_resets_previous_mode(self):
        c=self.fake_client();config=list(range(13))
        c.configure(config,'digital-zero',7)
        self.assertEqual(c.requests[-1],(4,config+[1,7]))
        c.configure(config)
        self.assertEqual(c.requests[-1],(4,config+[0,32]))

    def test_digital_zero_rejects_legacy_and_missing_capability(self):
        for version,cap in ((0x10000,0),(0x10001,0)):
            c=self.fake_client(version,cap)
            with self.assertRaisesRegex(RuntimeError,'BOOT.BIN'):
                c.configure([0]*13,'digital-zero')
            self.assertFalse(c.requests)

    def test_configuration_readback_mismatch_is_not_accepted(self):
        c=self.fake_client();read=c.read
        c.read=lambda offset,count=1: (0,32) if offset==0x84 else read(offset,count)
        with self.assertRaisesRegex(RuntimeError,'read-back'):
            c.configure([0]*13,'digital-zero',5)

    def test_rate_conversion_and_zero_rate_rejection(self):
        w=[0]*32;w[0]=0x46525131;w[5]=80000000;w[12]=16000
        self.assertEqual(h.decode_record(struct.pack('<32I',*w),'frequency')['latency_us'],200)
        w[5]=0
        with self.assertRaisesRegex(ValueError,'positive'):h.decode_record(struct.pack('<32I',*w),'frequency')
        with self.assertRaisesRegex(ValueError,'positive'):self.fake_client(rate=0).hardware_info()
        with self.assertRaisesRegex(ValueError,'positive'):h.decode_record(burst_record(rate=0),'burst')

    def test_boundary_flags_and_length_meaning(self):
        r=h.decode_record(burst_record(flags=(1<<12)|(1<<13)|(1<<8)),'burst')
        self.assertEqual(r['detector_mode'],'digital-zero')
        self.assertEqual(r['length_semantics'],'数字零背景波形长度')
        self.assertFalse(r['start_confirmed']);self.assertFalse(r['end_confirmed'])
        r=h.decode_record(burst_record(flags=0),'burst')
        self.assertEqual(r['length_semantics'],'门限突发长度')

    def test_finite_reference_uses_zero_edges_and_rejects_old_threshold(self):
        data=b''.join(struct.pack('<hh',i,0) for i in [0,0,0,0,1,1,1,0,0,0,0])
        result=h.verify_finite_digital_zero(data,[burst_record()],gap_min=4)
        self.assertEqual(result['status'],'PASS')
        with self.assertRaisesRegex(ValueError,'flags_raw'):
            h.verify_finite_digital_zero(data,[burst_record(flags=0)],gap_min=4)
        with self.assertRaisesRegex(ValueError,'count'):
            h.verify_finite_digital_zero(data,[],gap_min=4)

    def test_export_preserves_detector_provenance(self):
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            h.export(tmp,[],[burst_record()],{'source':'Synthetic test','hardware_version':0x10001,'gap_min':4})
            meta=json.loads((Path(tmp)/'capture.json').read_text(encoding='utf-8'))
            record=json.loads((Path(tmp)/'burst.json').read_text(encoding='utf-8'))[0]
            self.assertEqual(meta['detector_mode'],'digital-zero')
            self.assertEqual(meta['sample_rate_hz'],100000000)
            self.assertEqual(meta['hardware_version'],0x10001);self.assertEqual(meta['gap_min'],4)
            self.assertEqual(record['length_semantics'],'数字零背景波形长度')

    def test_invalid_detector_settings(self):
        for gap in (0,65536,-1,1.5):
            with self.assertRaises(ValueError):h.validate_detector('digital-zero',gap)
        with self.assertRaises(ValueError):h.validate_detector('unknown',32)

    def test_extended_identity_and_unsupported_record_format(self):
        c=self.fake_client(version=0x10002,capabilities=3);original=c.read
        c.read=lambda offset,count=1: (1,2,3,4,100000000,1,4) if offset==0x90 else original(offset,count)
        self.assertEqual(c.hardware_info()['build_id'],'00000004000000030000000200000001')
        c.read=lambda offset,count=1: (1,2,3,4,100000000,2,4) if offset==0x90 else original(offset,count)
        with self.assertRaisesRegex(RuntimeError,'record format'):c.hardware_info()
        with self.assertRaisesRegex(RuntimeError,'major version'):self.fake_client(version=0x20000).hardware_info()

    def test_diagnostic_snapshot_counter_width(self):
        c=self.fake_client()
        values=[0,1,0,1,0,12,5,6,0,1,0,1,524288,0,0]
        c.read=lambda offset,count=1: {0x134:(1,),0x138:(7,),0x140:values}[offset]
        d=c.diagnostics()
        self.assertEqual(d['issued_samples'],2**32)
        self.assertEqual(d['fft_input_samples'],2**32)
        self.assertEqual(d['fft_snapshot_arrival_tick'],5+6*2**32)


if __name__=='__main__':unittest.main()
