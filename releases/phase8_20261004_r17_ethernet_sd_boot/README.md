# Phase 8 r17 Ethernet SD boot image

`BOOT.BIN` is the SD-card boot image for the PC-to-board UDP streaming workflow. It contains the shared FPGA bitstream and the r16 UDP firmware; the r17 host sender runs on the PC.

`BOOT_sd.BIN` is an alternate image for the finite SD-card self-test. Use only one image as `BOOT.BIN` on the card at a time. This package currently keeps `BOOT.BIN` set to the Ethernet streaming image.

The images were generated with Vitis Bootgen 2026.1 and parsed back with `bootgen -read`. Before installing, preserve the card's existing `BOOT.BIN`. After cold boot, verify build ID `bae26b27515a813bbef3093a68992465`, then run the r17 DMA validation from the PC with source address `192.168.1.20`.

This package has not yet been written to a physical SD card. The host currently exposes no removable SD volume.
