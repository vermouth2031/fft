"""Bind existing GUI presets to explicit local references for the active profile."""
import argparse
import datetime
import json
from pathlib import Path
import shutil
from record_build_stage import ROOT,sha
from validate_measurements import load_index
from phase4_prepare_bandwidth import load_index as load_ofdm


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--robust-index',type=Path,required=True);p.add_argument('--ofdm-index',type=Path,required=True)
    p.add_argument('--ofdm-case',required=True);p.add_argument('--status',choices=['pending','qualified'],required=True)
    a=p.parse_args();robust_path=a.robust_index.resolve();ofdm_path=a.ofdm_index.resolve()
    assert robust_path.is_relative_to(ROOT/'build') and ofdm_path.is_relative_to(ROOT/'build')
    robust=next(r for r in load_index(robust_path)['cases'] if r['case']['id']=='robust_snr5_120000')
    ofdm=next(r for r in load_ofdm(ofdm_path)['cases'] if r['case']['id']==a.ofdm_case and
              json.loads(Path(r['reference']).read_text())['mode']=='hann')
    path=ROOT/'data/phase4_demo/presets.json';data=json.loads(path.read_text(encoding='utf-8'))
    backup=ROOT/'build/phase5/demo_updates'/datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    backup.mkdir(parents=True,exist_ok=False);shutil.copyfile(path,backup/'presets_before.json')
    profile=json.loads((ROOT/'config/build_profile.json').read_text());fs=profile['sample_rate_hz']
    for row in data['presets']:
        if row['id']=='robust':
            source=Path(robust['vector']);reference=robust_path.parent/robust['reference']
        elif row['id']=='ofdm':
            source=Path(ofdm['vector']);reference=Path(ofdm['reference'])
            row.update(cyclic=ofdm['case']['replay']=='cyclic',seconds=ofdm['case']['seconds'],
                meaning=f"{fs/1e6:g} MSPS，设计跨度 {ofdm['case']['design_span_mhz']:g} MHz；99% 占用带宽以实测内部窗为准，边沿窗另列。")
            if a.status=='pending':row['meaning']+=' 当前候选宽带矩阵仍在验收。'
        else:
            source=ROOT/'data/vectors'/('burst_fs4.bin' if row['id']=='digital' else 'tone_pos_fs4.bin');reference=None
            if row['id']=='tone':row['meaning']=f'{fs/4e6:g} MHz 单音，展示谱峰及分辨率限制标志。'
        assert source.resolve().is_relative_to(ROOT) and source.is_file()
        if reference:assert reference.resolve().is_relative_to(ROOT) and reference.is_file()
        destination=ROOT/'data/phase4_demo'/source.name
        if destination.exists():shutil.copyfile(destination,backup/destination.name)
        shutil.copyfile(source,destination)
        row.update(vector=destination.relative_to(ROOT).as_posix(),sha256=sha(destination),
            source_vector=source.relative_to(ROOT).as_posix(),reference=reference.relative_to(ROOT).as_posix() if reference else None,
            reference_sha256=sha(reference) if reference else None)
    data.update(build_id=json.loads((ROOT/'build/config/build_identity.json').read_text())['build_id'],
                sample_rate_hz=fs,qualification_status=a.status)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (backup/'update.json').write_text(json.dumps(dict(status='PASS',current_presets_sha256=sha(path),
        robust_index_sha256=sha(robust_path),ofdm_index_sha256=sha(ofdm_path),source_sha256=sha(Path(__file__))),indent=2)+'\n')
    print('PHASE5_DEMO_REFERENCES_BOUND',fs,a.status)


if __name__=='__main__':main()
