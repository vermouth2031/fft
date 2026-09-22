"""Exercise rejection of stale, partial and incorrectly advertised board identities."""
import json
from phase4_identity import ROOT, check_identity

identity = json.loads((ROOT / 'build/config/build_identity.json').read_text())
p = identity['profile']
hardware = dict(p)
hardware['hardware_capabilities'] = hardware.pop('capabilities')
hardware['build_id'] = identity['build_id']
check_identity(hardware)
for key in hardware:
    bad = dict(hardware)
    bad[key] = '0' * 32 if key == 'build_id' else bad[key] + 1
    try:
        check_identity(bad)
    except ValueError:
        pass
    else:
        raise AssertionError('Accepted stale field ' + key)
    bad.pop(key)
    try:
        check_identity(bad)
    except ValueError:
        pass
    else:
        raise AssertionError('Accepted missing field ' + key)
print('BUILD_IDENTITY_GUARDS_PASS', len(hardware) * 2 + 1)
