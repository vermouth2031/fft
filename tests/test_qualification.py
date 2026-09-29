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
        from types import SimpleNamespace
        import iq_client
        from qualification_capture import capture
        from threshold_config import resolve
        detector=dict(DEFAULT_DETECTOR,ton=2**33+123,toff=2**32+456)
        received=[]
        def fake_capture(args):
            received.append(resolve(args,bytes(32768*4))[0])
        with patch.object(iq_client,'capture',fake_capture):
            capture(SimpleNamespace(detector='threshold',gap_min=32),detector)
        self.assertEqual(received,[detector])

    def test_production_threshold_profiles_and_conflicts(self):
        from types import SimpleNamespace
        from threshold_config import resolve
        data=np.tile(np.array([[3,4]],dtype='<i2'),(8192,1)).tobytes()
        d,meta=resolve(SimpleNamespace(threshold_profile='robust'),data)
        self.assertEqual((d['ton'],d['toff'],d['kon'],d['koff']),(1200,700,16,8))
        self.assertEqual(meta['estimated_background_power'],25)
        d,_=resolve(SimpleNamespace(),data)
        self.assertEqual(d,DEFAULT_DETECTOR)
        for args in [dict(ton=10),dict(ton=2,toff=3),dict(kon=0),
                     dict(threshold_profile='robust',ton=1,toff=0),
                     dict(threshold_profile='robust',quiet_samples=8193),
                     dict(detector='digital-zero',threshold_profile='robust')]:
            with self.assertRaises(ValueError):resolve(SimpleNamespace(**args),data)

    def test_noise_only_has_explicit_power_and_no_snr(self):
        from make_phase2_specs import case
        c=case('noise_only',{'kind':'zero'},intervals=[],seed=130000,policy='quiet-prefix')
        c['noise']={'kind':'awgn','power_codes2':2*1024**2}
        _,iq,meta=waveform_details(c)
        self.assertEqual(meta['truth_intervals'],[])
        self.assertNotIn('measured_snr_after_quantization_db',meta)
        self.assertLess(abs(meta['measured_noise_power_codes2']/(2*1024**2)-1),.03)
        self.assertTrue(np.any(iq))

    def test_capture_configuration_readback_rejects_any_mismatch(self):
        from types import SimpleNamespace
        from iq_client import verify_capture_config
        config=[32768,1,1,0,8191,123,2,45,1,16,8,1048576,0]
        expected=[config[0],0,*config[1:12]]
        def client(values):
            def read(offset,count):
                self.assertEqual((offset,count),(0x1c,13))
                return values
            return SimpleNamespace(read=read)
        self.assertEqual(verify_capture_config(client(expected),config),expected)
        for i in range(13):
            changed=list(expected);changed[i]^=1
            with self.assertRaisesRegex(RuntimeError,'before START'):
                verify_capture_config(client(changed),config)

    def test_zero_quiet_background_can_confirm_burst_end(self):
        from types import SimpleNamespace
        from threshold_config import resolve
        from make_phase2_specs import case,tone
        c=case('quiet_zero',tone(amplitude=8),intervals=[[2048,4096]],policy='quiet-prefix',windows=['hann'])
        c['threshold_policy'].update(on_multiple=3,off_multiple=1.75)
        c['detector'].update(kon=16,koff=8)
        _,iq,details=waveform_details(c)
        applied,_=resolve(SimpleNamespace(threshold_profile='robust'),iq.tobytes())
        self.assertEqual(applied,details['applied_detector'])
        self.assertEqual((applied['ton'],applied['toff']),(2,1))
        bursts=reference_threshold(iq,applied)
        self.assertEqual(len(bursts),1)
        self.assertEqual((bursts[0]['start_sample'],bursts[0]['end_sample'],bursts[0]['flags']),(2048,4111,0))


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
