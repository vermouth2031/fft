connect
targets -set -filter {name =~ "ARM*#0"}
mrd -bin -file D:/fft/fft_phase10_resource_opt/build/phase10_dma_debug.bin 0x002017c0 16384
disconnect
