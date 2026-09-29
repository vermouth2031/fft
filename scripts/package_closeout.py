"""Deliver the frozen Phase 4 hardware plus separately qualified GUI changes.

This does not refresh or relax the original full-system qualification gates.
Run --check before committing; then --out release/phase4-closeout-20260928
from a clean checkout. The complete frozen archive is required.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit
import zipfile

from record_build_stage import ROOT, inputs, sha, verify
from record_boot_stage import verify_boot
from phase4_check_links import audit

BASE_NAME = 'phase4-complete-20260922'
BASE_SHA = '4e07fbc86a0768464a6923da5d096b288c8b15b7334f0840005291d2ec0d5b53'
REPORT = ROOT / 'reports/closeout_20260928'
CAPTURE = ROOT / 'captures/gui_closeout_20260928'
GUI_FILES = {'host/monitor.py', 'host/monitor_view.py'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def safe(root, name):
    path = (root / name).resolve()
    require(path.is_relative_to(root.resolve()), 'Path escapes root: ' + str(name))
    return path


def validate():
    archive = ROOT / 'release' / (BASE_NAME + '.zip')
    require(sha(archive) == BASE_SHA, 'Frozen complete archive changed')
    with zipfile.ZipFile(archive) as z:
        base = json.loads(z.read('manifest.json'))
    verify('hardware')
    verify_boot()
    complete = read(ROOT / 'reports/phase4_complete_validation.json')
    require(complete['status'] == 'PASS', 'Frozen hardware acceptance failed')
    for name, digest in complete['artifacts'].items():
        require(sha(ROOT / 'artifacts' / name) == digest, 'Hardware artifact changed: ' + name)
    for name, digest in complete['evidence'].items():
        require(sha(safe(ROOT, name)) == digest, 'Frozen hardware evidence changed: ' + name)

    previous = read(ROOT / 'reports/simulation_provenance.json')
    current = inputs('simulation')
    changed = sorted(n for n in set(previous['inputs']) | set(current)
                     if previous['inputs'].get(n) != current.get(n))
    require(set(changed) == GUI_FILES, 'Change exceeds qualified GUI scope: ' + str(changed))
    for section in ('artifacts', 'evidence'):
        for name, digest in previous.get(section, {}).items():
            require(sha(safe(ROOT, name)) == digest, 'Frozen simulation evidence changed: ' + name)
    # Reject all other changes to the frozen implementation, tools and inputs.
    protected = ('rtl/', 'constraints/', 'firmware/', 'host/', 'tests/', 'scripts/',
                 'config/', 'vendor/', 'data/', 'artifacts/', 'reports/')
    for name, record in base['files'].items():
        if name.startswith(protected) and name not in GUI_FILES:
            require(sha(safe(ROOT, name)) == record['sha256'], 'Frozen implementation changed: ' + name)

    gui_path = CAPTURE / 'gui_validation.json'
    gui = read(gui_path)
    require(gui['status'] == 'PASS' and len(gui['tests']) == 18, 'Incomplete GUI qualification')
    require(gui['hardware'] == complete['hardware'], 'GUI tested another hardware build')
    require(gui['cleanup']['status'] == 'PASS' and gui['cleanup']['board_stopped'], 'GUI did not clean up')
    require((REPORT / 'gui_validation.json').read_bytes() == gui_path.read_bytes(), 'Published GUI report differs')
    for name, digest in gui['source_sha256'].items():
        require(sha(safe(ROOT, name)) == digest, 'GUI-tested source changed: ' + name)
    for name, digest in gui['frozen_reports_sha256'].items():
        path = Path(name).resolve()
        require(path.is_relative_to(ROOT) and sha(path) == digest, 'Frozen report changed: ' + name)
    for name, digest in gui['files_sha256'].items():
        require(sha(safe(CAPTURE, name)) == digest, 'GUI raw evidence changed: ' + name)
    board_rows = [r for r in gui['tests'] if 'capture' in r]
    require(len(board_rows) == 4 and all(r['status'] == 'PASS' for r in gui['tests']), 'GUI case failed')
    for row in board_rows:
        require(row['numerical_verification']['status'] == 'PASS', 'Board numerical check failed')
        meta = row['metadata']
        require(meta['capture_complete'] and meta['throughput_conservation_valid']
                and meta['udp_missing_packet_count'] == 0 and meta['error_status'] == 0,
                'Board integrity check failed')
        vector = Path(meta['vector']).resolve()
        require(vector.is_relative_to(ROOT) and sha(vector) == meta['vector_sha256'], 'Board input changed')
    host = read(REPORT / 'host_checks.json')
    require(host['status'] == 'PASS' and len(host['tests']) == 5, 'Host checks incomplete')
    for row in host['tests']:
        require(row['status'] == 'PASS' and sha(safe(ROOT, row['log'])) == row['log_sha256'], 'Host log changed')
    source_files = {p.relative_to(ROOT).as_posix(): sha(p)
                    for folder in ('host', 'tests') for p in (ROOT / folder).glob('*.py')}
    source_files['scripts/package_closeout.py'] = sha(Path(__file__))
    source_files.update(gui['source_sha256'])
    evidence = {p.relative_to(ROOT).as_posix(): sha(p) for p in
                (gui_path, REPORT / 'gui_validation.json', REPORT / 'host_checks.json')}
    evidence.update({r['log']: r['log_sha256'] for r in host['tests']})
    return dict(status='PASS', hardware=gui['hardware'], frozen_archive_sha256=BASE_SHA,
                frozen_source_commit=base['source_commit'], changed_simulation_inputs=changed,
                scope='Frozen hardware acceptance plus current GUI/acquisition regression; not a new full-system simulation, matrix or physical cold boot',
                gui_tests=18, board_cases=4, source_files=source_files, evidence=evidence,
                maximum_analysis_us=max(r['numerical_verification']['maximum_analysis_us'] for r in board_rows),
                maximum_publish_us=max(r['numerical_verification']['maximum_publish_us'] for r in board_rows))


def documentation(root):
    result = audit(root)
    for name in ('项目工程总结.md', 'docs/新版上位机使用说明.md', 'docs/GitHub维护说明.md',
                 'reports/closeout_20260928/收尾验收说明.md'):
        path = root / name
        result['documents'][name] = sha(path)
        text = re.sub(r'```.*?```', '', path.read_text(encoding='utf-8'), flags=re.S)
        for target in re.findall(r'!?\[[^\]]*\]\(([^\s)]+)\)', text):
            parsed = urlsplit(target)
            if parsed.scheme in ('http', 'https', 'mailto') or target.startswith('#'):
                continue
            candidate = (path.parent / unquote(parsed.path)).resolve()
            if parsed.scheme or not candidate.is_relative_to(root) or not candidate.exists():
                result['errors'].append(dict(document=name, link=target, error='missing or non-portable'))
            else:
                result['checked_links'].append(dict(document=name, link=target))
    result['status'] = 'FAIL' if result['errors'] else 'PASS'
    require(result['status'] == 'PASS', 'Documentation errors: ' + str(result['errors']))
    return result


def package(out, validation):
    require(out.is_relative_to(ROOT / 'release') and not out.exists()
            and not out.with_suffix('.zip').exists(), 'Choose a new directory under release/')
    require(not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT), 'Commit all changes before delivery')
    require(read(REPORT / 'validation.json') == validation, 'Recheck the final source before committing')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    out.mkdir(parents=True)
    files, replaced, line_endings = {}, {}, {}

    def add_bytes(name, data):
        destination = safe(out, name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        files[name] = dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())

    print('Extracting and checking every frozen archive entry', flush=True)
    with zipfile.ZipFile(ROOT / 'release' / (BASE_NAME + '.zip')) as z:
        manifest_bytes = z.read('manifest.json')
        base = json.loads(manifest_bytes)
        require(set(z.namelist()) == set(base['files']) | {'manifest.json'}, 'Unexpected frozen entries')
        for name, record in base['files'].items():
            data = z.read(name)  # Also verifies each entry's CRC.
            require(len(data) == record['bytes'] and hashlib.sha256(data).hexdigest() == record['sha256'],
                    'Frozen archive entry differs: ' + name)
            add_bytes(name, data)
        add_bytes('historical/frozen_phase4/manifest.json', manifest_bytes)

    def overlay(name, data):
        if name in files and hashlib.sha256(data).hexdigest() != files[name]['sha256']:
            old = (out / name).read_bytes()
            original = 'historical/frozen_phase4/' + name
            add_bytes(original, old)
            replaced[name] = original
        add_bytes(name, data)

    print('Adding committed source and current GUI evidence', flush=True)
    names = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode('utf-8').split('\0')
    for name in filter(None, names):
        data = subprocess.check_output(['git', 'show', 'HEAD:' + name], cwd=ROOT)
        working = (ROOT / name).read_bytes()
        if working != data:
            require(working.replace(b'\r\n', b'\n') == data.replace(b'\r\n', b'\n'),
                    'Checkout content differs from commit: ' + name)
            line_endings[name] = dict(git_blob_sha256=hashlib.sha256(data).hexdigest(),
                                     packaged_sha256=hashlib.sha256(working).hexdigest())
        overlay(name, working)
    for path in CAPTURE.rglob('*'):
        if path.is_file():
            add_bytes(path.relative_to(ROOT).as_posix(), path.read_bytes())
    overlay('START_HERE.md', '''# 2026-09-28 项目收尾交付

先阅读 [项目工程总结](项目工程总结.md) 和 [收尾验收说明](reports/closeout_20260928/收尾验收说明.md)。
双击 `Open_IQ_Monitor.cmd` 使用新版界面；已安装正确网络镜像的板卡无需重新烧写。

本包包含9月22日完整硬件证据、五组信号、新版上位机与9月28日实板回归。硬件仍为100 MSPS、8192点FFT、八路扫描。
本次18项界面回归包括4项数值核验通过的实板采集；没有重新执行完整硬件矩阵或物理断电验收。

在解压目录运行 `python scripts/verify_delivery.py .` 核验逐文件散列。
当前源码提交见 `manifest.json` 的 `source_commit`，完整验证范围见 `validation_scope`。
历史冻结文件被更新时，其原始字节保存在 `historical/frozen_phase4/`；旧报告中的散列仍对应旧版本。
旧完整系统打包门禁不因界面测试而自动通过。若修改电路、固件或通信协议，应重新构建并完成对应硬件验收。

原始采集位于 `captures/gui_closeout_20260928`；报告中的绝对路径保留采集环境，包内相对路径用于查阅。
软件构建和SD维护历史记录仍可能引用原电脑的组合构建目录，重建需配置本地工具并产生新证据。
'''.encode('utf-8'))
    links = documentation(out)
    overlay('documentation_links.json', (json.dumps(links, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    manifest = dict(schema='iq-phase4-gui-closeout-v1',
                    created_at=datetime.datetime.now().astimezone().isoformat(),
                    hardware_version=validation['hardware']['hardware_version_hex'],
                    build_id=validation['hardware']['build_id'], source_commit=commit,
                    frozen_source_commit=validation['frozen_source_commit'], frozen_archive_sha256=BASE_SHA,
                    validation_scope=validation['scope'], gui_regression_tests=18, new_board_cases=4,
                    new_full_hardware_matrix=False, new_physical_cold_boot=False,
                    frozen_hardware_acceptance='reports/phase4_complete_validation.json',
                    current_gui_acceptance='reports/closeout_20260928/validation.json',
                    preserved_frozen_files=replaced, checkout_line_endings=line_endings, files=files)
    write(out / 'manifest.json', manifest)
    subprocess.run([sys.executable, str(ROOT / 'scripts/verify_delivery.py'), str(out)], check=True)
    subprocess.run([sys.executable, str(out / 'scripts/check_five_signals_archive.py')], cwd=out, check=True)
    archive = out.with_suffix('.zip')
    print('Compressing complete delivery', flush=True)
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for name in sorted(files):
            z.write(out / name, name)
        z.write(out / 'manifest.json', 'manifest.json')
    print('Verifying all ZIP entry hashes and CRCs', flush=True)
    with zipfile.ZipFile(archive) as z:
        require(len(z.namelist()) == len(files) + 1 and set(z.namelist()) == set(files) | {'manifest.json'}, 'ZIP entries differ')
        for name, record in files.items():
            with z.open(name) as stream:
                require(hashlib.file_digest(stream, 'sha256').hexdigest() == record['sha256'], 'ZIP content differs: ' + name)
        require(z.read('manifest.json') == (out / 'manifest.json').read_bytes(), 'ZIP manifest differs')
    require(sha(ROOT / 'release' / (BASE_NAME + '.zip')) == BASE_SHA, 'Frozen archive changed during packaging')
    require(validate() == validation, 'Source or evidence changed during packaging')
    result = dict(status='PASS', source_commit=commit, archive=str(archive), directory=str(out),
                  bytes=archive.stat().st_size, sha256=sha(archive), file_count=len(files) + 1,
                  crc_checked=True, all_archive_sha256_checked=True, frozen_archive_unchanged=True)
    write(out.parent / (out.name + '_check.json'), result)
    print(json.dumps(result, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--check', action='store_true')
    group.add_argument('--out', type=Path)
    args = parser.parse_args()
    validation = validate()
    if args.check:
        write(REPORT / 'validation.json', validation)
        try:
            documentation(ROOT)
        except Exception:
            write(REPORT / 'validation.json', dict(validation, status='FAIL', documentation='FAIL'))
            raise
        print('CLOSEOUT_QUALIFICATION_PASS', flush=True)
    else:
        package(args.out.resolve(), validation)


if __name__ == '__main__':
    main()
