# Volatile diagnostic marker in the documented software-owned REBOOT_STATE.
# Clear old reset-reason flags so a later reset can be distinguished from them.
connect
targets -set -filter {name =~ "ARM*#0"}
puts "BEFORE [mrd 0xf8000258]"
mwr 0xf8000258 0x5a000000
puts "AFTER [mrd 0xf8000258]"
disconnect
