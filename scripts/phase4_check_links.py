"""Check portable local links in the current delivery's reader-facing documents."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

DOCUMENTS = (
    'README.md', 'reports/第四阶段完整验收报告.md', 'reports/最终电路设计说明.md',
    'reports/第四阶段时钟可行性结论.md', 'reports/冷启动验证报告.md',
    'reports/帧长度定义与误差分析.md', 'reports/答辩材料/讲稿与预计提问.md',
    'docs/phase4_registers.md', 'scripts/maintenance/操作说明.md',
    'THIRD_PARTY_NOTICES.md',
)

def audit(root):
    root = Path(root).resolve()
    documents = list(DOCUMENTS)
    if (root/'START_HERE.md').is_file(): documents.append('START_HERE.md')
    checked = []
    errors = []
    hashes = {}
    for name in documents:
        source = root/name
        if not source.is_file():
            errors.append({'document': name, 'error': 'missing document'})
            continue
        hashes[name] = hashlib.sha256(source.read_bytes()).hexdigest()
        text = re.sub(r'```.*?```', '', source.read_text(encoding='utf-8'), flags=re.S)
        for match in re.finditer(r'!?\[[^\]]*\]\((<[^>]*>|[^\s)]+)(?:\s+"[^"]*")?\)', text):
            target = match.group(1).strip('<>')
            if target.startswith('#'): continue
            if re.match(r'^(https?://|mailto:)', target): continue
            parsed = urlsplit(target)
            candidate = (source.parent/unquote(parsed.path)).resolve()
            row = {'document': name, 'link': target}
            if parsed.scheme or not candidate.is_relative_to(root):
                errors.append(row | {'error': 'non-portable path'})
            elif not candidate.exists():
                errors.append(row | {'error': 'missing target'})
            else:
                checked.append(row | {'target': candidate.relative_to(root).as_posix()})
    return {'status': 'FAIL' if errors else 'PASS',
            'scope': 'Current reader-facing documents; historical plans and archived reports retain their original context.',
            'documents': hashes, 'checked_links': checked, 'errors': errors}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path, nargs='?', default=Path(__file__).resolve().parents[1])
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    result = audit(args.root)
    text = json.dumps(result, ensure_ascii=False, indent=2)+'\n'
    if args.out: args.out.write_text(text, encoding='utf-8')
    print(text)
    raise SystemExit(result['status'] != 'PASS')
