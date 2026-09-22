"""Exercise the actual preset wrapper, production callbacks and frozen oracles."""
import argparse
import json
from pathlib import Path
from phase4_demo import ROOT,DemoMonitor,presets,monitor
from check_monitor_board import GuiAcceptance
from package_release import check
from package_validated import check_board
from record_build_stage import sha

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    check();check_board();a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=False)
    original=monitor.ROOT;monitor.ROOT=a.out
    monitor.enable_dpi_awareness();root=monitor.tk.Tk();app=DemoMonitor(root)
    runner=GuiAcceptance(root,app,a.out,'192.168.1.10')
    runner.report['wrapper_sha256']=sha(ROOT/'scripts/phase4_demo.py')
    try:
        for row in presets():
            app.apply_preset(row)
            assert app.vector.get()==str(ROOT/row['vector']) and app.detector.get()==row['detector']
            folder=runner.capture(row['id'],row['detector'],str(ROOT/row['vector']),row['cyclic'],
                3 if row['cyclic'] else 1,threshold_profile=row['profile'],
                qualification=ROOT/row['reference'] if row.get('reference') else None)
        runner.offline(folder);runner.report['status']='PASS'
    except Exception as e:
        runner.report.update(status='FAIL',error=str(e));raise
    finally:
        runner.report['cleanup']=runner.cleanup();runner.save();root.destroy();monitor.ROOT=original
    print('PHASE4_DEMO_GUI_PASS',a.out)
if __name__=='__main__':main()
