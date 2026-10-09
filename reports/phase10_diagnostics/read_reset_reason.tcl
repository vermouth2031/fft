connect
targets -set -filter {name =~ "ARM*#0"}
puts [mrd 0xf8000250 4]
disconnect
