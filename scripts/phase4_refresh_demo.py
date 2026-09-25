"""Bind the four demonstration presets to the accepted final build's references."""
import json
from pathlib import Path
import shutil
from record_build_stage import ROOT,sha
from phase4_final_campaign import REFS,CAPTURES

def main():
    campaign=json.loads((CAPTURES/'phase4_campaign.json').read_text())
    assert campaign['status']=='PASS','Complete the final board campaign first'
    path=ROOT/'data/phase4_demo/presets.json'
    backup=ROOT/'build/phase4_demo_before_final.json'
    assert not backup.exists(),'Demo update already started; inspect the saved version'
    shutil.copy2(path,backup)
    data=json.loads(path.read_text(encoding='utf-8'))
    for row in data['presets']:
        if row['id']=='robust':
            source=REFS/'regression/validation/vectors/robust_snr5_120000.bin'
            reference=REFS/'regression/validation/references/robust_snr5_120000_hann.json'
        elif row['id']=='ofdm':
            source=REFS/'widest/continuous/vectors/ofdm_b98p14_qpsk_s212100_f0_t10.bin'
            reference=REFS/'widest/continuous/references/ofdm_b98p14_qpsk_s212100_f0_t10_hann.json'
            row['meaning']='设计跨度约 98.14 MHz；99% 占用带宽使用全部 8192 点功率谱，边沿窗另列。'
        else:
            source=ROOT/row['source_vector'];reference=None
        destination=ROOT/'data/phase4_demo'/source.name
        assert source.is_file()
        shutil.copy2(source,destination)
        assert sha(source)==sha(destination)
        row.update(vector=destination.relative_to(ROOT).as_posix(),sha256=sha(destination),
                   source_vector=source.relative_to(ROOT).as_posix(),
                   reference=reference.relative_to(ROOT).as_posix() if reference else None,
                   reference_sha256=sha(reference) if reference else None)
    data['build_id']=json.loads((ROOT/'reports/current_board_validation.json').read_text())['hardware']['build_id']
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('PHASE4_DEMO_PRESETS_BOUND_TO_FINAL_REFERENCES')

if __name__=='__main__':main()
