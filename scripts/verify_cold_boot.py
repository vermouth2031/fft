"""Network-only acceptance AFTER an explicitly user-confirmed physical power cycle."""
import argparse
import contextlib
import datetime
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'host'))
from iq_client import Client,capture
from package_release import check
from package_validated import check_board,require
from record_boot_stage import verify_boot
from record_build_stage import sha
from verify_board_capture import verify


def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def now():return datetime.datetime.now().astimezone().isoformat()


def state(board):
    client=Client(board)
    try:
        return dict(hardware=client.hardware_info('digital-zero'),state=client.read(8)[0]&7,
                    errors=client.read(0x60)[0],epoch=client.read(0x68)[0])
    finally:client.close()


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('--board',default='192.168.1.10')
    p.add_argument('--user-confirmation',required=True,help='Actual user statement confirming a fresh physical power-off/on; never infer it from a software reset')
    a=p.parse_args();check();verify_boot();accepted=check_board()
    sd_path=ROOT/'reports/sd_boot_update.json';sd=json.loads(sd_path.read_text(encoding='utf-8'))
    board_hash=sha(ROOT/'reports/current_board_validation.json')
    require(sd['status']=='PASS' and sd['sd_write_verified'] and sd['boot_medium_verified'],'Current SD installation/reset not verified')
    require(sd['jtag_board_validation_sha256']==board_hash and sd['image_sha256']==sha(ROOT/'artifacts/BOOT_udp.BIN'),'SD evidence belongs to another build')
    require(a.user_confirmation.strip() and accepted['board']==a.board,'Missing physical-cycle statement or different board')
    out=a.out.resolve();require(out.is_relative_to(ROOT/'captures'),'Use a project captures directory')
    out.mkdir(parents=True,exist_ok=False)
    report=dict(status='RUNNING',started_at=now(),board=a.board,power_cycle_evidence=a.user_confirmation,
        jtag_used=False,program_download_performed=False,scope='Network identification and exact captures after user-confirmed physical power cycle',
        previous_sd_update_sha256=sha(sd_path),previous_board_validation_sha256=board_hash,
        artifacts={n:sha(ROOT/'artifacts'/n) for n in ('BOOT_udp.BIN','iq_analyzer.bit','iq_udp.elf')},folder=str(out),cases=[])
    try:
        before=state(a.board)
        require(before['hardware']==accepted['hardware'] and before['state']==0 and before['errors']==0,'Cold-start board is not idle/clean/matching')
        require(before['epoch']==0,'Board has already acquired data since reset; request a fresh physical cycle')
        report.update(hardware_before=before['hardware'],state_before=0,errors_before=0,epoch_before=before['epoch'])
        for name,detector,vector,seconds in (('digital_zero_finite','digital-zero','burst_fs4',0),
                ('threshold_finite','threshold','burst_fs4',0),('digital_zero_continuous_3s','digital-zero','qpsk_sps4',3)):
            folder=out/name;log=out/(name+'.log')
            with log.open('w',encoding='utf-8') as stream,contextlib.redirect_stdout(stream):
                capture(SimpleNamespace(board=a.board,port=5001,vector=str(ROOT/'data/vectors'/(vector+'.bin')),
                    out=str(folder),window='hann',cyclic=bool(seconds),seconds=seconds or 1,detector=detector,gap_min=32))
            row=verify(folder)
            require(row['maximum_analysis_us']<=accepted['maximum_analysis_us']+1.0,
                    'Cold-start analysis latency is inconsistent with the accepted implementation')
            save(folder/'measurement_validation.json',row)
            row.update(case=name,measurement_report_sha256=sha(folder/'measurement_validation.json'),capture_log_sha256=sha(log))
            report['cases'].append(row)
            print('COLD_BOOT_CASE_PASS',name,flush=True)
        after=state(a.board)
        require(after['state']==0 and after['errors']==0,'Post-cold-start capture left an error')
        report.update(status='PASS',hardware_after=after['hardware'],state_after=0,errors_after=0,
            frequency_records=sum(x['frequency_records'] for x in report['cases']),
            burst_records=sum(x['burst_records'] for x in report['cases']),
            exact_snapshot_values=sum(x['exact_snapshot_values'] for x in report['cases']),
            maximum_analysis_us=max(x['maximum_analysis_us'] for x in report['cases']),
            maximum_publish_us=max(x['maximum_publish_us'] for x in report['cases']))
    except Exception as error:
        report.update(status='FAIL',error=str(error));raise
    finally:
        report['finished_at']=now();save(out/'cold_boot_validation.json',report)
        save(ROOT/'reports/current_cold_boot_validation.json',report)
    (ROOT/'reports/冷启动验证报告.md').write_text(
        '# 冷启动验证报告\n\n'+f"验证时间：{report['finished_at']}。用户确认：{a.user_confirmation}\n\n"
        '验证程序只使用网络读回和采集，没有使用JTAG或下载程序。启动后首次epoch为0。\n\n'
        f"三个用例全部通过，共{report['frequency_records']}条频域记录、{report['burst_records']}条突发记录；"
        f"最大分析延迟{report['maximum_analysis_us']:.2f}µs，结束状态空闲、错误寄存器为0。\n\n"
        f"当前BOOT_udp.BIN SHA-256：`{report['artifacts']['BOOT_udp.BIN']}`。\n\n"
        '物理断电行为依据用户确认；当前硬件没有运行时bitstream散列寄存器，身份由已验证SD读回、启动流程及数值验收共同绑定。\n',encoding='utf-8')
    print('COLD_BOOT_PASS',out)


if __name__=='__main__':main()
