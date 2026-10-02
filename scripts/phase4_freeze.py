"""Freeze the accepted Phase 3 baseline without changing current evidence."""
import datetime
import json
from pathlib import Path
import subprocess
import zipfile
from record_build_stage import ROOT, sha
from package_release import check
from record_boot_stage import verify_boot
from package_validated import check_board, supplementary_evidence, require
from validate_measurements import configuration


def main():
    check(); verify_boot(); check_board(); supplementary_evidence()
    package=ROOT/'release/phase3-complete-20260922.zip'
    require(sha(package)=='1c2dc16ff59d063ae871dcf3c9f03617661b33c34d306a3e6a08da0f6deeb84c','Baseline ZIP changed')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    require(commit=='f871b999d642e7d4a76a070b7b48b48d3790073c','Unexpected baseline commit')
    info=configuration('192.168.1.10',5001)
    require(info['state']&7==0 and info['hardware']['sample_rate_hz']==100000000,'Board not idle/matching')
    out=ROOT/'build/phase4_baseline_20260922';out.mkdir(parents=True,exist_ok=False)
    subprocess.run(['git','archive','--format=zip','--output',str(out/'source.zip'),commit],cwd=ROOT,check=True)
    with zipfile.ZipFile(out/'reports_and_logs.zip','w',zipfile.ZIP_DEFLATED) as z:
        for folder in ('reports','build/logs'):
            for p in (ROOT/folder).rglob('*'):
                if p.is_file():z.write(p,p.relative_to(ROOT))
    files=[p for p in (ROOT/'artifacts').glob('*') if p.is_file()]+[package,ROOT/'第四阶段优化实施方案.md']
    report=dict(status='PASS',created_at=datetime.datetime.now().astimezone().isoformat(),commit=commit,
        user_authorization='真板已连接，按照方案继续进行优化',rules_reply='没有新说明，按现有题面继续',
        hardware=info,files={p.relative_to(ROOT).as_posix():sha(p) for p in files},
        archives={p.relative_to(ROOT).as_posix():sha(p) for p in out.glob('*.zip')})
    (out/'baseline.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (ROOT/'reports/phase4_baseline.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    questions=[('input','IQ信号数据速率≥100MSPS','板内预装载回放，每拍一对IQ'),
        ('fft_ip','完成对应功能RTL电路设计','AMD FFT内核，自有测量与控制RTL'),
        ('frame','测量帧长度','突发包络的样本区间'),('frequency','测量频点','谱峰，带宽中心另列'),
        ('bandwidth','数字IQ信号带宽，MHz','完整谱99%占用带宽'),
        ('latency','接收IQ至得出频域信息≤2ms','PL窗口首个IQ至板内结果，另列环形缓冲发布时间')]
    rules=dict(source=str(ROOT.parent/'赛道2_FPGA设计及应用赛题整理.md'),
        source_sha256=sha(ROOT.parent/'赛道2_FPGA设计及应用赛题整理.md'),user_reply=report['rules_reply'],
        official_confirmation_received=False,items=[dict(id=i,requirement=q,current_interpretation=v,
            status='UNCONFIRMED_BY_ORGANIZER',confirmation_source=None,confirmation_date=None) for i,q,v in questions])
    (ROOT/'reports/phase4_requirements.json').write_text(json.dumps(rules,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('PHASE4_BASELINE_PASS',out)


if __name__=='__main__':main()
