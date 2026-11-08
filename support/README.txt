Phase13 portable reproduction entry (no Git repository required)

1. Copy/extract the COMPLETE source directory to a short ASCII-only path, e.g.
   D:\phase13\project
   The Chinese submission folder is an archive layout, not a Vivado build path.
2. Install Vivado/Vitis 2026.1 and Python 3.12; install requirements.txt.
   AMD FFT bit-accurate C model comes from the installed Vivado distribution.
3. From the ASCII project directory run:
   powershell -NoProfile -ExecutionPolicy Bypass -File support\rebuild.ps1 -Action All
   Python defaults to the python executable on PATH. Use Python 3.12.
   Tool paths can be overridden with -VivadoRoot, -VitisRoot and -Python.
   -Python accepts an executable name on PATH or an absolute/relative path;
   rebuild resolves it before starting stages and rejects missing executables.
4. Stages can be resumed individually using -Action (or -Stage):
   Reference -> Hardware -> Software -> Sim -> Finalize
   All runs every stage; it does not silently reuse successful stage results.
   Keep data/qualification and reports/phase13_baseline.json from this package.

The entry temporarily clears IQ_CLIENT_SOURCE_IP while running offline build
and regression stages, so a previously configured board-NIC address cannot
break loopback protocol tests. The original environment setting is restored
on success or failure; the user's normal board-capture configuration is kept.

Software uses support/run_software.py -> Vitis -s support/vitis_compat.py ->
the unchanged scripts/build_software.py. A local adapter handles only the
vitis-server stdout stream: UTF-8 is tried first, then strict CP936 decoding.
Raw bytes, decoded diagnostics and the server command are retained under
build/logs/vitis_server_*.log. Invalid decoding and real server/build failures
still fail the stage. No AMD installation file is modified. Vitis output is
captured by Python to build/logs/build_software.log; SOFTWARE_BUILD_PASS and
absence of Traceback are required, together with a successful process exit.

The supported workflow calls Reference/Hardware/Sim of scripts/run.ps1;
Software uses the launcher above. Finalize checks fresh provenance, inspects
the newly routed replay RAM enables, checks Phase13 limits, runs Bootgen and
records boot provenance. It needs no .git directory.

scripts/run.ps1 -Action All forwards to this complete workflow; -Action Package
forwards to Finalize. Historical release/deployment tools remain in this Git
repository for traceability; this supported workflow does not invoke them.
validate_measurements.py retains reference preparation and shared numerical
checks; use the Phase13 board commands in README.md for capture and validation.
Historical phase numbers still present in retained filenames identify tools
or regression references used by this release. Keep them in their locations.

Logs: build/logs/support_*.log and the original stage logs in build/logs/.
Outputs: artifacts/iq_analyzer.bit, iq_analyzer.xsa, iq_udp.elf, iq_sd.elf,
zynq_fsbl.elf, ps7_init.tcl, BOOT_udp.BIN and BOOT_sd.BIN.
IMPORTANT: artifacts/BOOT.BIN follows the original build convention and is a
copy of BOOT_sd.BIN (standalone SD-test application). For NETWORK auto-start,
the correct image is BOOT_udp.BIN, renamed BOOT.BIN on the target SD card.

Building does not program hardware or write SD/QSPI. Board deployment and
finite/continuous numerical validation are separate and must be recorded as
new evidence. Do not substitute old board reports for a new board test.
