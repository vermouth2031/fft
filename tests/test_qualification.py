"""Qualification oracle regression and explicit refusal of unsupported evidence."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from fft_reference import FFTReference, N, FS, digest
from generate_qualification_vectors import waveform, validate_case, generate
from make_golden import generate as generate_golden

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from validate_measurements import load_manifest, verify_configuration, prepare, error_rows
from verify_board_capture import verify
from threshold_reference import reference_threshold
from generate_qualification_vectors import DEFAULT_DETECTOR, waveform_details
from detection_metrics import evaluate


class QualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = json.loads((ROOT/'data/qualification/s1_pilot.json').read_text())

    def test_import_is_inert(self):
        with tempfile.TemporaryDirectory() as folder:
            code = f'''import sys, numpy
from unittest.mock import patch
sys.path.insert(0, {str(ROOT/'tests')!r})
with patch('pathlib.Path.mkdir', side_effect=AssertionError('import mkdir')), patch('zipfile.ZipFile', side_effect=AssertionError('import extraction')), patch('ctypes.CDLL', side_effect=AssertionError('import DLL')):
    import fft_reference, make_golden
'''
            subprocess.run([sys.executable, '-c', code], cwd=folder, check=True)
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_legacy_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            generate_golden(folder)
            for name in ('golden_fft.mem','test_iq.mem','golden_results.json','hann_u18_f17.mem'):
                self.assertEqual((ROOT/'data'/name).read_bytes(), (Path(folder)/name).read_bytes(), name)

    def test_model_boundaries_and_lifetime(self):
        with self.assertRaises(ValueError):
            FFTReference(sample_rate_hz=125000000)
        with FFTReference() as model:
            zero, packed, shot = model.window(np.zeros((N,2), dtype=np.int16))
            self.assertEqual(zero['total'], 0)
            self.assertFalse(np.any(packed))
            self.assertFalse(np.any(shot))
            dc, _, _ = model.window(np.full((N,2), -32768, dtype=np.int64))
            self.assertEqual(dc['q_peak'], 4096)
            self.assertEqual(dc['energy'], N*2*32768**2)
            for invalid in (np.zeros((N-1,2),dtype=int), np.zeros((N,2)), np.full((N,2),32768)):
                with self.assertRaises(ValueError):
                    model.window(invalid)
            with self.assertRaises(ValueError):
                model.window(np.zeros((N,2),dtype=int),'blackman')
        model.close()
        with self.assertRaises(RuntimeError):
            model.window(np.zeros((N,2),dtype=int))

    def test_generator_rejects_unsupported_and_overflow(self):
        for key,value in [('sample_rate_hz',125000000),('replay','cyclic'),('samples',123),
                          ('noise',{'kind':'awgn'}),('windows',['hann','hann'])]:
            case=copy.deepcopy(self.spec['cases'][0]);case[key]=value
            with self.assertRaises(ValueError):
                waveform(case)
        case=copy.deepcopy(self.spec['cases'][0]);case['signal']['tones'][0]['amplitude']=40000
        with self.assertRaises(ValueError):
            waveform(case)
        case=copy.deepcopy(self.spec['cases'][0]);case['detector']['ton']=1
        with self.assertRaises(ValueError):
            validate_case(case)

    def test_manifest_integrity_and_unique_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/'vectors'
            path=generate(ROOT/'data/qualification/s1_pilot.json',out)
            manifest=load_manifest(path)
            with self.assertRaises(FileExistsError):
                generate(ROOT/'data/qualification/s1_pilot.json',out)
            binary=out/manifest['cases'][0]['binary']
            data=bytearray(binary.read_bytes());data[0]^=1;binary.write_bytes(data)
            with self.assertRaisesRegex(ValueError,'hash mismatch'):
                load_manifest(path)

    def test_explicit_oracle_on_real_legacy_capture_and_corruption(self):
        # Reuse a recorded physical-board result, never fabricate a record from its oracle.
        source=ROOT/'data/qualification/legacy_capture_fixture'
        origin=json.loads((source/'origin.json').read_text())
        for name, expected in origin['files'].items():
            self.assertEqual(digest(source/name),expected)
        vector=ROOT/'data/vectors'/(origin['vector_case']+'.bin')
        self.assertEqual(digest(vector),origin['input_sha256'])
        meta=json.loads((source/'capture.json').read_text())
        mode=__import__('iq_client').decode_record((source/'frequency.bin').read_bytes()[:128],'frequency')['window']
        chosen=next(c for c in json.loads((ROOT/'data/golden_results.json').read_text())['cases']
                    if c['name']==origin['vector_case'] and c['mode']==mode)
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            for name in ('capture.json','frequency.bin','burst.bin'):
                shutil.copyfile(source/name,folder/name)
            renamed=folder/'arbitrary_name.bin'
            shutil.copyfile(vector,renamed)
            from generate_qualification_vectors import DEFAULT_DETECTOR
            oracle=dict(schema='iq-qualification-reference-v1',input_sha256=digest(renamed),
                sample_rate_hz=FS,detector=DEFAULT_DETECTOR,mode=mode,windows=chosen['windows'],
                bindings={str(ROOT/'tests/fft_reference.py'):digest(ROOT/'tests/fft_reference.py')})
            path=folder/'reference.json'
            path.write_text(json.dumps(oracle))
            self.assertEqual(verify(folder,renamed,qualification=path)['status'],'PASS')
            oracle['windows']=copy.deepcopy(oracle['windows'])
            oracle['windows'][0]['total']+=1
            path.write_text(json.dumps(oracle))
            with self.assertRaisesRegex(ValueError,'total_spectrum_power'):
                verify(folder,renamed,qualification=path)
            meta['cyclic']=True
            (folder/'capture.json').write_text(json.dumps(meta))
            with self.assertRaisesRegex(ValueError,'finite replay'):
                verify(folder,renamed,qualification=path)

    def test_error_table_from_real_capture(self):
        case=next(c for c in self.spec['cases'] if c['id']=='integer_p2048')
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            spec=folder/'spec.json'
            spec.write_text(json.dumps(dict(schema='iq-qualification-spec-v1',cases=[case])))
            manifest=generate(spec,folder/'vectors')
            index_path=prepare(manifest,folder/'reference')
            index=json.loads(index_path.read_text())
            oracle=json.loads((index_path.parent/index['cases'][0]['reference']).read_text())
            rows=error_rows(ROOT/'data/qualification/legacy_capture_fixture',index['cases'][0]['case'],oracle)
            self.assertEqual([r['window_id'] for r in rows],[0,1,2,3])
            for row in rows:
                self.assertEqual(row['frequency_error_hz'],0)
                self.assertEqual(row['hardware_peak_codes'],8192)
                self.assertEqual(row['hardware_rms_codes'],8192)
                self.assertTrue(row['nearest_bin_match'])

    def test_threshold_model_matches_all_legacy_vectors(self):
        from verify_board_capture import burst_expectations
        manifest=json.loads((ROOT/'data/vectors/reference_manifest.json').read_text())
        for c in manifest['cases'].values():
            iq=np.fromfile(ROOT/'data/vectors'/c['binary'],dtype='<i2').reshape(-1,2)
            self.assertEqual(reference_threshold(iq,DEFAULT_DETECTOR),
                             burst_expectations(iq,'threshold',32,1048576,True))
        iq=np.zeros((8192,2),dtype=np.int16);iq[40:104,0]=4
        detector=dict(DEFAULT_DETECTOR,ton=4,toff=2,kon=1,koff=1)
        got=reference_threshold(iq,detector)
        self.assertEqual((got[0]['start_sample'],got[0]['end_sample']),(40,119))
        self.assertEqual(got[0]['energy'],64*16)

    def test_detection_misses_merges_splits_and_false_alarms(self):
        merged=evaluate([[100,200],[300,400]],[[95,405]],1000)
        self.assertEqual((merged['matched'],merged['missed'],merged['merged_detections'],merged['normal_matches']),(1,1,1,0))
        split=evaluate([[100,200]],[[100,150],[150,200],[500,550]],1000)
        self.assertEqual((split['matched'],split['split_truths'],split['false_alarms'],split['normal_matches']),(1,1,1,0))
        exact=evaluate([[100,200]],[[100,200]],1000)
        self.assertEqual(exact['normal_detection_rate'],1)

    def test_seed_snr_filter_truth_and_quiet_policy(self):
        from make_phase2_specs import build
        stages=build();case=stages['s2_training'][1]
        floating,iq,design=waveform_details(case)
        self.assertTrue(np.array_equal(iq,waveform_details(case)[1]))
        self.assertLess(abs(design['measured_snr_before_quantization_db']-case['noise']['snr_db']),.2)
        self.assertGreater(design['applied_detector']['ton'],design['applied_detector']['toff'])
        changed=copy.deepcopy(case);changed['seed']+=10
        self.assertFalse(np.array_equal(iq,waveform_details(changed)[1]))
        shaped=stages['s3_finite'][0]
        _,_,meta=waveform_details(shaped)
        self.assertEqual(meta['symbol_intervals'],[[4096,28672]])
        self.assertEqual(meta['shaped_intervals'],[[4096,28692]])
        self.assertGreater(meta['component_headroom_codes'],0)
        changed=copy.deepcopy(case);changed['threshold_policy']['samples']=4096
        with self.assertRaises(ValueError):waveform_details(changed)

    def test_qualification_config_payload_and_readback(self):
        from unittest.mock import patch
        import iq_client
        from qualification_capture import capture
        detector=dict(DEFAULT_DETECTOR,ton=2**33+123,toff=2**32+456)
        meta={}
        class FakeClient:
            def configure(self,config,*args):self.config=config
            def read(self,offset,count):return self.config[5:12]
        def fake_capture(args):
            client=iq_client.Client();client.configure([32768,0,1,0,8191]+[0]*8,'threshold',32,meta)
        with patch.object(iq_client,'Client',FakeClient),patch.object(iq_client,'capture',fake_capture):
            capture(None,detector)
        self.assertEqual(meta['applied_detector'],detector)
        self.assertEqual(meta['threshold_registers_before_start'][:4],[123,2,456,1])


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(QualificationTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        sys.exit(1)
    report=dict(status='PASS',tests=result.testsRun,legacy_cases=16,exact_fft_points=524288,
                compatibility='All four legacy output files are byte-identical',
                sources={str(p.relative_to(ROOT)):digest(p) for p in
                    (Path(__file__),ROOT/'tests/fft_reference.py',ROOT/'tests/make_golden.py',
                     ROOT/'tests/generate_qualification_vectors.py',ROOT/'scripts/validate_measurements.py',
                     ROOT/'scripts/verify_board_capture.py',ROOT/'data/qualification/s1_pilot.json',
                     ROOT/'tests/threshold_reference.py',ROOT/'tests/detection_metrics.py',
                     ROOT/'scripts/qualification_capture.py',ROOT/'tests/make_phase2_specs.py')})
    (ROOT/'reports/qualification_tool_validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('QUALIFICATION_TOOLS_PASS')
