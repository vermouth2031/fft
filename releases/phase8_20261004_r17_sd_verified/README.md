# Phase 8 r17 SD verified release

This independent release retains the r17 PC UDP sender and the SD boot image. The SD card was written and read back by SHA-256, installed in the Zybo Z7-20, and cold-booted after a full power removal. The resulting board identity and 12-switch smoke test plus 1000-switch DMA acceptance are recorded under `reports/`.

Build ID: `bae26b27515a813bbef3093a68992465`

BOOT.BIN SHA-256: `1f07038642b609a01da5f6e6b67d09f4045181b2c3f3651ce09d994b4663f4f8`

The prior card image is retained at `reports/sd_backup/BOOT_before_update.BIN`. The r17 candidate directory and its Git tag remain unchanged.
