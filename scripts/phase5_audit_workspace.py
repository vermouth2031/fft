"""Verify active build, reference and maintenance paths belong to this checkout."""
import argparse
import json
from pathlib import Path
import sys

from package_release import check
from record_build_stage import ROOT, sha


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--references-root', type=Path, required=True)
    a = p.parse_args()
    check()
    software = json.loads((ROOT / 'reports/software_validation.json').read_text())
    workspace = Path(software['workspace']).resolve()
    if not workspace.is_relative_to(ROOT / 'build'):
        raise ValueError('Software still depends on another checkout: ' + str(workspace))
    sys.path.insert(0, str(ROOT / 'scripts/maintenance'))
    from sd_boot_update import discover
    actual_workspace, compiler, xsdb, bsp = discover()
    if actual_workspace != workspace or not bsp.is_relative_to(workspace):
        raise ValueError('Maintenance does not use the current software workspace')
    for source, built in (('echo.c', 'iq_udp/src/echo.c'), ('sd_main.c', 'iq_sd/src/main.c')):
        if sha(ROOT / 'firmware' / source) != sha(workspace / built):
            raise ValueError('Built firmware differs from current sources')
    refs = a.references_root.resolve()
    if not refs.is_relative_to(ROOT / 'build'):
        raise ValueError('Reference root is outside this checkout')
    # The AMD numerical oracle archive is an intentional installed-tool input.
    vivado = Path(r'D:\VivadoMM\2026.1\Vivado').resolve()
    paths = set()
    files = []
    for path in refs.rglob('index.json'):
        data = json.loads(path.read_text(encoding='utf-8'))
        for name, digest in data.get('bindings', {}).items():
            dep = Path(name).resolve()
            if not (dep.is_relative_to(ROOT) or dep.is_relative_to(vivado)):
                raise ValueError('External worktree reference dependency: ' + str(dep))
            if sha(dep) != digest:
                raise ValueError('Stale reference dependency: ' + str(dep))
            paths.add(str(dep))
        files.append(dict(path=str(path), sha256=sha(path)))
    if not files:
        raise ValueError('No generated reference indices')
    report = dict(status='PASS', workspace=str(ROOT), software_workspace=str(workspace),
                  maintenance_bsp=str(bsp), compiler=str(compiler), xsdb=str(xsdb),
                  reference_indices=files, dependency_paths=sorted(paths),
                  source_sha256=sha(Path(__file__)),
                  scope='Active build and selected references use this checkout; historical reports are retained as history',
                  limitation='Does not remove installed Vivado/Vitis dependencies or claim an archive is relocatable without rebuilding')
    (ROOT / 'reports/phase5_workspace_audit.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PHASE5_WORKSPACE_AUDIT_PASS', len(files), len(paths))


if __name__ == '__main__':
    main()
