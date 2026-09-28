"""Separate GUI regression evidence; never rewrites frozen hardware acceptance.

Run from the project root with an idle board:
  python scripts/check_monitor_redesign.py --out captures/gui_redesign_NEW
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'host'), str(ROOT / 'scripts')]
import tkinter as tk
import monitor
from check_monitor_board import GuiAcceptance, require
from iq_client import Client, decode_record
from phase4_demo import DemoMonitor


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_display(app):
    """Compare presentation to decoded board records, including complete metadata."""
    update = app._last_update
    record, burst = update['record'], update.get('latest_burst')
    expected = {
        'amplitude': f"{record['rms_codes']:.3f}",
        'length': f"{burst['length_us']:.2f}" if burst else '—',
        'frequency': f"{record['peak_hz']/1e6:.6f}",
        'bandwidth': f"{record['bandwidth_hz']/1e6:.6f}",
    }
    require({k: v.get() for k, v in app.card_values.items()} == expected,
            'Measurement cards differ from the selected board record')
    require(json.loads(app.raw_text.get('1.0', 'end')) == update,
            'Raw record or metadata was omitted')
    details = app.detail_text.get('1.0', 'end').strip()
    require(details == app.metrics.get().strip(), 'Legacy measurement text was omitted')
    for text in ('RMS', '峰值', '峰频率', '99% 带宽', '带宽中心', 'PL 分析延迟',
                 'I16/Q16', 'FFT', '窗口', '已收频域', '突发', '标志'):
        require(text in details, 'Missing original GUI field: ' + text)
    require(app.requirements.item('rate', 'values')[2] == f"{record['sample_rate_hz']/1e6:g} MSPS",
            'Requirements page sample rate differs from actual record')
    require(app.requirements.item('fft', 'values')[2] == f"{record['fft_length']} 点",
            'Requirements page FFT length differs from actual record')


def offline_checks(runner):
    app, root = runner.app, runner.root
    archive = ROOT / 'reports/five_signals_20260923/board'
    for signal in ('tone', 'two_tone', 'chirp', 'qpsk', 'ofdm'):
        for window in ('rect', 'hann'):
            folder = archive / f'{signal}_{window}'
            app.load_capture(folder)
            runner.pump()
            expected = decode_record((folder / 'frequency.bin').read_bytes()[-128:], 'frequency')
            require(app._last_update['record'] == expected, 'Wrong historical record')
            check_display(app)
            require(app.window.get() == window, 'Historical window selection was not restored')
            require(app.view_mode == 'offline' and not (app.worker and app.worker.is_alive()),
                    'Offline viewing unexpectedly acquired data')
            runner.report['tests'].append(dict(name=f'offline_{signal}_{window}', status='PASS'))

    # Check all pages on both normal and minimum-size windows, with saved screenshots.
    for geometry in ('1240x920', '900x720'):
        root.geometry(geometry + '+15+15')
        for key in app.pages:
            app.tabs.select(app.pages[key])
            runner.pump()
            require(app.status_label.winfo_y() + app.status_label.winfo_height()
                    <= root.winfo_height(), 'Status message is outside the window')
            if key != 'details':
                viewport = getattr(app, key + '_viewport')
                viewport.yview_moveto(0)
            runner.screenshot(f'{geometry}_{key}.png')
            if key != 'details':
                viewport.yview_moveto(1)
                runner.pump()
                require(viewport.yview()[1] >= .999, 'Bottom of page is not reachable')
                if geometry == '900x720':
                    runner.screenshot(f'{geometry}_{key}_bottom.png')
                viewport.yview_moveto(0)
    runner.report['tests'].append(dict(name='all_pages_and_small_window_scroll', status='PASS'))

    # Missing input must not silently show the previously selected signal.
    fixture = runner.out / 'missing_input_fixture'
    fixture.mkdir()
    source = archive / 'tone_rect'
    for name in ('frequency.bin', 'burst.bin', 'snapshot.json'):
        if (source / name).exists():
            shutil.copyfile(source / name, fixture / name)
    meta = json.loads((source / 'capture.json').read_text(encoding='utf-8-sig'))
    meta['vector'] = str(fixture / 'does_not_exist.bin')
    (fixture / 'capture.json').write_text(json.dumps(meta), encoding='utf-8')
    app.load_capture(fixture)
    runner.pump()
    require(not app.vector.get() and not hasattr(app.env, '_last_plot'),
            'Missing historical input reused an unrelated envelope')
    check_display(app)
    runner.report['tests'].append(dict(name='missing_input_keeps_measurements_without_fake_envelope', status='PASS'))

    app.detector.set('digital-zero')
    app.threshold_profile.set('robust')
    app.threshold_policy.set('quiet-prefix')
    app.threshold_values['ton'].set('12345')
    app.detector_selected()
    require(app.threshold_profile.get() == 'legacy' and app.threshold_policy.get() == 'fixed'
            and all(not v.get() for v in app.threshold_values.values()),
            'Digital-zero selection left incompatible threshold overrides')
    runner.report['tests'].append(dict(name='detector_switch', status='PASS'))
    root.geometry('1240x920+15+15')
    app.tabs.select(app.pages['plots'])
    runner.pump()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--board', default='192.168.1.10')
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    frozen = {str(p): sha(p) for p in (ROOT / 'reports').glob('*.json')}
    source_files = ['host/monitor.py', 'host/monitor_view.py', 'host/iq_client.py',
                    'scripts/check_monitor_redesign.py']
    sources = {name: sha(ROOT / name) for name in source_files}
    original_root, original_dialog = monitor.ROOT, monitor.messagebox.showerror
    root = runner = None
    failure = None
    try:
        accepted = json.loads((ROOT / 'reports/current_board_validation.json').read_text(encoding='utf-8'))
        client = Client(args.board)
        try:
            hardware = client.hardware_info('digital-zero')
            require(hardware == accepted['hardware'], 'Board identity differs from frozen acceptance')
            require(client.read(8)[0] & 7 == 0, 'Board is busy; do not interrupt another acquisition')
        finally:
            client.close()
        for name, digest in accepted['artifacts'].items():
            require(sha(ROOT / 'artifacts' / name) == digest, 'Hardware artifact changed: ' + name)
        # Host presentation changes require new evidence, not a rewrite of the frozen report.
        require(sources['host/iq_client.py'] == accepted['source_files']['host']['host/iq_client.py'],
                'Capture transport changed beyond the GUI regression scope')
        monitor.ROOT = out
        def fail_dialog(title, message, **kwargs):
            raise RuntimeError(f'{title}: {message}')
        monitor.messagebox.showerror = fail_dialog
        monitor.enable_dpi_awareness()
        root = tk.Tk()
        app = monitor.Monitor(root)
        runner = GuiAcceptance(root, app, out, args.board)
        runner.report.update(scope='GUI layout and acquisition regression only; frozen full-system acceptance unchanged',
                             source_sha256=sources, hardware=hardware,
                             frozen_reports_sha256=frozen)
        offline_checks(runner)
        print('OFFLINE_PASS: ten archived signal/window combinations and UI state checks', flush=True)

        real_start = app.start
        def checked_start():
            real_start()
            require(all(v.get() == '—' for v in app.card_values.values()), 'New run shows stale measurements')
            require(app._last_update is None, 'New run retains previous raw update')
            require(app.start_button.instate(['disabled']) and not app.stop_button.instate(['disabled']),
                    'Start/stop button states are incorrect')
            require(all(w.instate(['disabled']) for w, _ in app.config_widgets),
                    'Configuration remains editable during capture')
        app.start_button.configure(command=checked_start)
        cases = [('threshold_timed', 'threshold', 'qpsk_sps4.bin', True, 3, False),
                 ('digital_zero_finite', 'digital-zero', 'burst_fs4.bin', False, 1, False),
                 ('window_boundary_stop', 'digital-zero', 'qpsk_sps4.bin', True, 30, True)]
        for name, detector, vector, cyclic, seconds, stop in cases:
            original_update = app.show_update
            stop_pressed = []
            if stop:
                def press_stop(update):
                    original_update(update)
                    if not stop_pressed and not update.get('metadata'):
                        app.stop_button.invoke()
                        stop_pressed.append(True)
                app.show_update = press_stop
            runner.capture(name, detector, vector, cyclic, seconds, manual_stop=stop)
            app.show_update = original_update
            if stop:
                require(stop_pressed, 'Production stop button was not exercised')
            check_display(app)
            require(app.stop_button.instate(['disabled'])
                    and all(not w.instate(['disabled']) for w, _ in app.config_widgets),
                    'Controls were not restored after capture')
            print('BOARD_PASS: ' + name, flush=True)
        rows = json.loads((ROOT / 'data/phase4_demo/presets.json').read_text(encoding='utf-8'))['presets']
        robust = next(row for row in rows if row['id'] == 'robust')
        runner.capture('robust_5db_finite', 'threshold', str(ROOT / robust['vector']), False, 1,
                       threshold_profile='robust', qualification=ROOT / robust['reference'])
        check_display(app)
        print('BOARD_PASS: robust_5db_finite', flush=True)

        # The existing demonstration wrapper still uses the same variable/callback contract.
        demo_root = tk.Toplevel(root)
        demo = DemoMonitor(demo_root)
        demo.load_capture(ROOT / 'reports/five_signals_20260923/board/ofdm_rect')
        runner.pump()
        check_display(demo)
        demo_root.destroy()
        runner.report['tests'].append(dict(name='demo_wrapper_compatibility', status='PASS'))

        app.load_capture(ROOT / 'reports/five_signals_20260923/board/ofdm_rect')
        runner.screenshot('overview.png')
        app.tabs.select(app.pages['requirements'])
        runner.screenshot('requirements.png')
        require(all(sha(Path(p)) == digest for p, digest in frozen.items()), 'Frozen acceptance report changed')
        require(all(sha(ROOT / p) == digest for p, digest in sources.items()), 'Source changed during validation')
        runner.report['status'] = 'PASS'
    except BaseException as error:
        failure = error
        (out / 'gui_error.txt').write_text(traceback.format_exc(), encoding='utf-8')
        if runner:
            runner.report.update(status='FAIL', error=str(error))
    finally:
        if runner:
            try:
                cleanup = runner.cleanup()
            except BaseException as error:
                cleanup = dict(status='FAIL', reason=str(error))
            runner.report['cleanup'] = cleanup
            if cleanup['status'] != 'PASS':
                runner.report['status'] = 'FAIL'
                failure = failure or RuntimeError('Board idle cleanup was not verified')
            runner.report['finished_at'] = time.strftime('%Y-%m-%dT%H:%M:%S%z')
            runner.report['files_sha256'] = {p.relative_to(out).as_posix(): sha(p)
                for p in out.rglob('*') if p.is_file() and p.name not in ('gui_validation.json', 'gui_error.txt')}
            runner.save()
        if root:
            root.destroy()
        monitor.ROOT, monitor.messagebox.showerror = original_root, original_dialog
    if failure:
        raise SystemExit(f'GUI_REDESIGN_FAIL: {failure}; see {out}')
    print(f'GUI_REDESIGN_PASS: {out / "gui_validation.json"}')


if __name__ == '__main__':
    main()
