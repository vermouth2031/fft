"""Exercise the real Tk monitor against the board and save isolated evidence.

Run after programming matching hardware and firmware:
  python scripts/check_monitor_board.py --out captures/gui_YYYYMMDD_HHMMSS

Only the monitor's output root is redirected. GUI callbacks, capture transport,
reference checks and rendering execute their production implementations.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "host"), str(ROOT / "scripts")]
import tkinter as tk
from PIL import ImageGrab
import monitor
from iq_client import Client, DETECTOR_VERSION, LENGTH_SEMANTICS, decode_record
from verify_board_capture import verify
from package_release import check as check_build
from package_validated import check_board
from record_build_stage import sha


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


class GuiAcceptance:
    def __init__(self, root, app, out, board):
        self.root, self.app, self.out, self.board = root, app, out, board
        self.cancelled = False
        self.callback_error = None
        self.latest_update = None
        self.report = dict(source="Actual Tk GUI with Zybo UDP board capture",
                           board=board, status="RUNNING", tests=[], screenshots=[],
                           started_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
        original_update = app.show_update
        def observe_update(update):
            original_update(update)
            self.latest_update = update
        app.show_update = observe_update
        root.protocol("WM_DELETE_WINDOW", self.cancel)
        root.report_callback_exception = self.callback_failed

    def cancel(self):
        self.cancelled = True
        self.app.stop_event.set()

    def callback_failed(self, exception, value, tb):
        self.callback_error = "".join(traceback.format_exception(exception, value, tb))
        self.app.stop_event.set()

    def pump(self, cleanup=False):
        self.root.update()
        if not cleanup:
            require(not self.cancelled, "GUI acceptance cancelled; stopping capture")
            require(not self.callback_error, self.callback_error or "Tk callback failed")
        time.sleep(.02)

    def wait(self, predicate, timeout, description):
        deadline = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() >= deadline:
                raise TimeoutError(description)
            self.pump()
        self.pump()
        self.root.update_idletasks()

    def idle(self):
        return (self.app.worker is not None and not self.app.worker.is_alive()
                and self.app.messages.empty()
                and not self.app.start_button.instate(["disabled"]))

    def screenshot(self, name):
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        try:
            for _ in range(10):
                self.pump()
            left, top = self.root.winfo_rootx(), self.root.winfo_rooty()
            ImageGrab.grab(bbox=(left, top, left+self.root.winfo_width(),
                                top+self.root.winfo_height()),
                           all_screens=True).save(self.out / name)
        finally:
            self.root.attributes("-topmost", False)
        self.report["screenshots"].append(name)

    def capture(self, name, detector, vector, cyclic, seconds, manual_stop=False,
                threshold_profile='legacy', qualification=None):
        parent = self.out / "captures"
        parent.mkdir(exist_ok=True)
        before = set(parent.iterdir())
        # Production GUI filenames have one-second precision; avoid collisions.
        self.wait(lambda: not (parent / time.strftime("%Y%m%d_%H%M%S")).exists(),
                  3, "Waiting for a unique GUI capture directory")
        app = self.app
        app.board.set(self.board)
        app.vector.set(str(ROOT / "data/vectors" / vector))
        app.detector.set(detector)
        app.threshold_profile.set(threshold_profile)
        app.threshold_policy.set('quiet-prefix' if threshold_profile=='robust' else 'fixed')
        app.quiet_samples.set('1024')
        for value in app.threshold_values.values():
            value.set('')
        app.gap_min.set("32")
        app.cyclic.set(cyclic)
        app.window.set("hann")
        app.seconds.set(str(seconds))
        self.latest_update = None
        started = time.monotonic()
        previous_worker = app.worker
        app.start_button.invoke()
        require(app.worker is not previous_worker and app.worker is not None,
                "Start callback did not launch an acquisition worker")
        stop_requested = None
        if manual_stop:
            self.wait(lambda: self.latest_update is not None or self.idle(),
                      30, "No live GUI update before manual stop")
            require(app.worker.is_alive(), "Capture ended before the manual-stop test")
            stop_requested = time.monotonic()
            # The production window-boundary stop button uses this callback.
            app.stop_event.set()
        self.wait(self.idle, 120, f"{name}: worker or final GUI messages did not finish")
        duration = time.monotonic() - started
        after = set(parent.iterdir()) - before
        require(len(after) == 1, f"{name}: expected one new capture directory")
        folder = after.pop()
        meta = json.loads((folder / "capture.json").read_text(encoding="utf-8-sig"))
        require(meta.get("capture_complete") is True, f"{name}: incomplete capture: {meta}")
        require(meta.get("detector_mode") == detector and meta.get("gap_min") == 32,
                f"{name}: detector configuration did not reach the hardware")
        require(meta.get("hardware_version", 0) >= DETECTOR_VERSION,
                f"{name}: expected the new hardware version")
        require(self.latest_update is not None and self.latest_update.get("metadata") == meta,
                f"{name}: final metadata was not consumed by the GUI")
        require(len(app.env.find_all()) > 5 and len(app.spec.find_all()) > 5,
                f"{name}: envelope or spectrum was not rendered")
        verification = verify(folder, Path(vector) if qualification else None, qualification=qualification)
        if threshold_profile=='robust':
            require(meta['threshold_request']['profile']=='robust', 'GUI threshold profile did not reach capture')
            require((meta['applied_detector']['kon'],meta['applied_detector']['koff'])==(16,8),
                    'GUI confirmation lengths differ from robust profile')
            require('ton/toff=' in app.metrics.get() and 'kon/koff=16/8' in app.metrics.get(),
                    'Applied detector parameters are not visible in GUI')
        if detector == "digital-zero" and not cyclic:
            raw = (folder / "burst.bin").read_bytes()
            require(len(raw) == 64, "Finite burst_fs4 requires exactly one waveform record")
            burst = decode_record(raw, "burst")
            require((burst["start_sample"], burst["end_sample_exclusive"], burst["length_samples"])
                    == (2048, 26624, 24576), "Digital-zero waveform edges are not exact")
            require(burst["flags_raw"] == 1 << 12, "Finite waveform was not fully confirmed")
            require(meta.get("numerical_reference_validation", {}).get("status") == "PASS",
                    "Finite acquisition did not execute its built-in numerical reference check")
            require("24576" in app.metrics.get(), "Exact waveform length is not visible")
        require(LENGTH_SEMANTICS[detector] in app.metrics.get(),
                f"{name}: displayed length semantics disagree with the detector")
        if manual_stop:
            require(stop_requested is not None and stop_requested-started < seconds,
                    "Manual stop was requested after the timer")
            require(meta["input_samples"] / meta["sample_rate_hz"] < seconds / 2,
                    "Capture reached its timer instead of stopping on request")
        self.screenshot(name + ".png")
        self.report["tests"].append(dict(name=name, status="PASS", capture=str(folder),
                                         detector_mode=detector, cyclic=cyclic,
                                         manual_stop=manual_stop, elapsed_wall_seconds=duration,
                                         metadata=meta, numerical_verification=verification,
                                         gui_status=app.status.get(), gui_metrics=app.metrics.get()))
        self.save()
        return folder

    def offline(self, folder):
        folder = Path(folder).resolve()
        raw_file = next((folder / name for name in ("frequency.bin", "FREQ.BIN")
                         if (folder / name).exists()), None)
        require(raw_file is not None and raw_file.stat().st_size >= 128,
                "Offline frequency data is absent")
        require(raw_file.stat().st_size % 128 == 0, "Offline frequency data is truncated")
        with raw_file.open("rb") as stream:
            stream.seek(-128, 2)
            expected = decode_record(stream.read(128), "frequency")
        self.latest_update = None
        self.app.load_capture(folder)
        self.pump()
        require(self.latest_update is not None and self.latest_update["record"] == expected,
                "Offline GUI did not render the selected capture's last hardware record")
        require(not self.app.worker.is_alive(), "Offline viewing launched an acquisition")
        require(len(self.app.env.find_all()) > 5, "Offline envelope was not rendered")
        self.screenshot("offline_capture.png")
        self.report["tests"].append(dict(name="offline_capture", status="PASS", capture=str(folder),
                                         frequency_record=expected, gui_status=self.app.status.get(),
                                         gui_metrics=self.app.metrics.get()))
        self.save()

    def cleanup(self):
        """Always signal STOP and wait for the worker before destroying Tk."""
        self.app.stop_event.set()
        # All test captures are finite or at most 30 seconds, and the capture
        # implementation has bounded network retries. Keep pumping until its
        # finally/export path exits; do not leave a daemon acquisition behind.
        next_notice = time.monotonic() + 60
        while self.app.worker and self.app.worker.is_alive():
            try:
                self.pump(cleanup=True)
            except tk.TclError:
                time.sleep(.05)
            if time.monotonic() >= next_notice:
                print("GUI cleanup is waiting for the acquisition worker to stop and save.", flush=True)
                next_notice = time.monotonic() + 60
        for _ in range(10):
            self.pump(cleanup=True)
        client = Client(self.board)
        try:
            state = client.read(8)[0] & 7
            return dict(status="PASS" if state == 0 else "FAIL", worker_stopped=True,
                        board_state=state, board_stopped=state == 0)
        except Exception as error:
            return dict(status="FAIL", worker_stopped=True, board_stopped=None, reason=str(error))
        finally:
            client.close()

    def save(self):
        (self.out / "gui_validation.json").write_text(
            json.dumps(self.report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True,
                        help="New evidence directory; existing paths are rejected")
    parser.add_argument("--board", default="192.168.1.10")
    parser.add_argument("--offline-capture", type=Path,
                        help="Optional historical capture; defaults to the new finite capture")
    parser.add_argument('--robust-reference-index',type=Path,
                        help='Frozen qualification index for a real robust-profile GUI capture')
    args = parser.parse_args()
    check_build()
    accepted = check_board()
    require(accepted['board'] == args.board, 'Target differs from accepted board')
    accepted_identity = sha(ROOT / 'reports/current_board_validation.json')
    out = args.out.expanduser().resolve()
    if out.exists():
        parser.error(f"--out must be a new directory: {out}")
    if args.offline_capture is not None and not args.offline_capture.is_dir():
        parser.error("--offline-capture must be an existing capture directory")
    out.mkdir(parents=True, exist_ok=False)
    original_root = monitor.ROOT
    original_showerror = monitor.messagebox.showerror
    root = runner = failure = None

    def fail_dialog(title, message, **kwargs):
        raise RuntimeError(f"{title}: {message}")

    try:
        client = Client(args.board)
        try:
            require(client.read(0)[0] == 0x49514131, "Wrong FPGA design")
            client.hardware_info("digital-zero")
            require(client.read(8)[0] & 7 == 0, "GUI acceptance requires an idle board")
        finally:
            client.close()
        monitor.ROOT = out
        monitor.messagebox.showerror = fail_dialog
        monitor.enable_dpi_awareness()
        root = tk.Tk()
        app = monitor.Monitor(root)
        runner = GuiAcceptance(root, app, out, args.board)
        runner.capture("threshold_timed", "threshold", "qpsk_sps4.bin", True, 3)
        finite = runner.capture("digital_zero_finite", "digital-zero", "burst_fs4.bin", False, 1)
        runner.capture("window_boundary_stop", "digital-zero", "qpsk_sps4.bin",
                       True, 30, manual_stop=True)
        if args.robust_reference_index:
            from validate_measurements import load_index
            index=load_index(args.robust_reference_index)
            row=next(r for r in index['cases'] if r['case']['id']=='robust_snr5_120000')
            runner.capture('robust_5db_finite','threshold',row['vector'],False,1,
                threshold_profile='robust',qualification=args.robust_reference_index.parent/row['reference'])
        runner.offline(args.offline_capture or finite)
        runner.report["status"] = "PASS"
    except BaseException as error:
        failure = error
        (out / "gui_error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        if runner:
            runner.report.update(status="FAIL", error=str(error))
    finally:
        if runner:
            try:
                cleanup = runner.cleanup()
            except BaseException as error:
                cleanup = dict(status="FAIL", reason=str(error), worker_stopped=False)
            runner.report["cleanup"] = cleanup
            if cleanup["status"] != "PASS":
                runner.report["status"] = "FAIL"
                failure = failure or RuntimeError("GUI cleanup did not verify an idle board")
            runner.report["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            runner.save()
        elif failure:
            (out / "gui_validation.json").write_text(
                json.dumps(dict(status="FAIL", error=str(failure)), ensure_ascii=False, indent=2)
                + "\n", encoding="utf-8")
        if root:
            try:
                root.destroy()
            except tk.TclError:
                pass
        monitor.ROOT = original_root
        monitor.messagebox.showerror = original_showerror
    if failure:
        raise SystemExit(f"GUI_BOARD_FAIL: {failure}; see {out / 'gui_validation.json'}")
    check_build()
    check_board()
    require(accepted_identity == sha(ROOT / 'reports/current_board_validation.json'),
            'Accepted build changed during GUI acceptance')
    runner.report.update(current_board_validation_sha256=accepted_identity, folder=str(out),
                         files={p.relative_to(out).as_posix(): sha(p) for p in out.rglob('*')
                                if p.is_file() and (p.suffix == '.png' or p.name in
                                    ('capture.json', 'frequency.bin', 'burst.bin', 'snapshot.bin', 'snapshot.json'))})
    if args.offline_capture:
        runner.report['offline_files'] = {str(p.resolve()): sha(p) for p in args.offline_capture.iterdir()
                                         if p.name in ('capture.json', 'frequency.bin', 'burst.bin', 'snapshot.bin', 'snapshot.json')}
    runner.save()
    (ROOT / 'reports/current_gui_validation.json').write_text(
        json.dumps(runner.report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f"GUI_BOARD_PASS: {out / 'gui_validation.json'}")


if __name__ == "__main__":
    main()
