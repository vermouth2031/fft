"""Verify an extracted delivery against its included SHA-256 file manifest."""
from pathlib import Path
import argparse
import hashlib
import json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    folder = args.directory.resolve()
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    files = manifest['files']
    for name, record in files.items():
        path = (folder / name).resolve()
        if not path.is_relative_to(folder) or not path.is_file():
            raise ValueError(f'Missing or invalid delivery path: {name}')
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if path.stat().st_size != record['bytes'] or digest != record['sha256']:
            raise ValueError(f'Delivery content differs from manifest: {name}')
    print(f'DELIVERY_INTEGRITY_PASS files={len(files)} hardware={manifest["hardware_version"]}')
    print('Checks archive content integrity; does not rerun Vivado or hardware tests.')


if __name__ == '__main__':
    main()
