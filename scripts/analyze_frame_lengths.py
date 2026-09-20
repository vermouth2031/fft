"""Compare verified finite board records with the quantized waveform support."""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'host'), str(ROOT / 'tests')]
import numpy as np
from iq_client import decode_record
from frame_length_reference import reference_digital_zero
from record_build_stage import sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board-report', type=Path, default=ROOT / 'reports/current_board_validation.json')
    args = parser.parse_args()
    board = json.loads(args.board_report.read_text(encoding='utf-8'))
    if board['status'] != 'PASS' or board['suite'] != 'full':
        raise ValueError('Requires a passing full board acceptance report')
    rows = []
    selected = ('burst_fs4', 'short512_boundary', 'qpsk_sps4', 'qpsk_sps2')
    for case in board['cases']:
        folder = Path(case['folder'])
        meta = json.loads((folder / 'capture.json').read_text(encoding='utf-8'))
        vector = Path(meta['vector'])
        if meta['cyclic'] or vector.stem not in selected:
            continue
        for name, expected in case['files'].items():
            if sha(folder / name) != expected:
                raise ValueError(f'Changed board evidence: {folder / name}')
        if sha(vector) != case['input_sha256']:
            raise ValueError(f'Changed vector: {vector}')
        iq = np.fromfile(vector, dtype='<i2').reshape(-1, 2)
        truth = reference_digital_zero(iq[:, 0], iq[:, 1], gap_min=32)
        raw = (folder / 'burst.bin').read_bytes()
        measured = [decode_record(raw[n:n+64], 'burst') for n in range(0, len(raw), 64)]
        if len(truth) != 1 or len(measured) != 1 or truth[0]['flags'] != 4096:
            raise ValueError(f'Expected one confirmed, bounded waveform in {folder}')
        reference, actual = truth[0], measured[0]
        with (folder / 'frequency.bin').open('rb') as stream:
            window = decode_record(stream.read(128), 'frequency')['window']
        row = dict(vector=vector.stem, window=window, detector=meta['detector_mode'],
                   reference_start=reference['start_sample'], reference_end=reference['end_sample'],
                   reference_length=reference['length_samples'], measured_start=actual['start_sample'],
                   measured_end=actual['end_sample_exclusive'], measured_length=actual['length_samples'],
                   flags=actual['flags_raw'], folder=str(folder), input_sha256=case['input_sha256'])
        for field in ('start', 'end', 'length'):
            row[field + '_error_samples'] = row['measured_' + field] - row['reference_' + field]
            row[field + '_error_ns'] = row[field + '_error_samples'] * 1e9 / meta['sample_rate_hz']
        if row['detector'] == 'digital-zero' and any(row[f + '_error_samples'] for f in ('start', 'end', 'length')):
            raise ValueError(f'Digital-zero waveform boundary mismatch: {row}')
        rows.append(row)
    if len(rows) != 16:
        raise ValueError(f'Expected 16 selected finite cases, got {len(rows)}')
    report = dict(status='PASS', created_at=datetime.datetime.now().astimezone().isoformat(),
                  hardware_version=board['hardware']['hardware_version'], gap_min=32,
                  scope='Support intervals of quantized integer IQ, not protocol frame decoding',
                  board_report_sha256=sha(args.board_report), cases=rows)
    target = ROOT / 'reports/frame_length_validation.json'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    text = ['# 帧长度定义与误差分析', '',
            '本报告使用本轮完整实板验收的原始记录。真值来自量化后的 I16/Q16 非零区间，按连续32个零样本分隔；不是通信协议帧头解码。', '',
            '门限模式包含滑动能量与确认规则的边界偏移；数字零模式用于精确零背景。二者算法数值正确性已分别通过独立参考核验。本表进一步比较相对输入支撑区间的误差。', '',
            '| 波形 | 窗 | 模式 | 真值区间 [起,止) | 实测区间 [起,止) | 真值/实测长度 | 长度误差/点 | 长度误差/ns |',
            '|---|---|---|---|---|---|---:|---:|']
    for row in rows:
        text.append(f"| {row['vector']} | {row['window']} | {row['detector']} | "
                    f"[{row['reference_start']},{row['reference_end']}) | "
                    f"[{row['measured_start']},{row['measured_end']}) | "
                    f"{row['reference_length']}/{row['measured_length']} | "
                    f"{row['length_error_samples']} | {row['length_error_ns']:g} |")
    text += ['', '零背景模式所选8组的起点、终点和长度误差均为0点。每点10ns按100MHz标称时基换算，未作外部时基校准。', '',
             '不能从矩形突发的门限偏移推导所有输入固定补偿15点。噪声、偏置、包络和门限会改变检测区间。QPSK真值取决于滤波、量化和零间隔约定。', '',
             '采集从信号中途开始、停止时尚未确认结尾以及强制最大长度分段，通过明确标志表示；这些观测段不纳入本表完整波形误差统计。', '',
             '机器可读明细：[frame_length_validation.json](frame_length_validation.json)。原始文件位置与SHA-256保留在该报告及当前板测报告中。', '']
    (ROOT / 'reports/帧长度定义与误差分析.md').write_text('\n'.join(text), encoding='utf-8')
    print('FRAME_LENGTH_BOARD_PASS', len(rows), target)


if __name__ == '__main__':
    main()
