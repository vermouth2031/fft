set root [file normalize [file join [file dirname [info script]] ..]]
set_param board.repoPaths [list $root/vendor/boards]
open_project $root/build/board/iq_board.xpr
file mkdir $root/artifacts
write_hw_platform -fixed -force -file $root/artifacts/iq_analyzer_pre.xsa
close_project
