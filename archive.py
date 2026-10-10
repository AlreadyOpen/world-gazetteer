"""Archive the whole release on Kaggle, one immutable dataset per PlaceDB release (helenkwok/world-gazetteer-<release>): the
files as delivered (release/, api/v1/, LIMITATIONS.md) and the derived ones. Then download it back and check every file's
sha256 against the local copy; only then does it write kaggle-verified.json, which publish.py needs before it replaces the
previous release on Hugging Face. A dataset that already exists is never versioned, only verified again.
Needs KAGGLE_API_TOKEN in the environment (a repo secret; never on argv).
Usage: python3 archive.py     (after bake.py)"""
import hashlib, json, os, subprocess, sys, tempfile, time
import kaggle_mirror, publish, sources

FILES = ['release', 'api', 'LIMITATIONS.md', 'places.parquet', 'divisions.parquet', 'places.pmtiles', 'index.json', 'releases.json']


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
    return h.hexdigest()


def tree(root):
    out = {}
    for top in FILES:
        p = os.path.join(root, top)
        if os.path.isfile(p): out[top] = p
        for d, _, fs in os.walk(p, followlinks=True):
            for f in fs: out[os.path.relpath(os.path.join(d, f), root)] = os.path.join(d, f)
    return out


def main():
    idx, _ = publish.checked()                                         # the publish gate first: nothing is archived past it
    v = idx['release']; slug = f'helenkwok/world-gazetteer-{v.lower()}'; title = f'AlreadyOpen: world gazetteer {v}'
    if subprocess.run(['kaggle', 'datasets', 'files', slug], capture_output=True).returncode != 0:
        kaggle_mirror.mirror(slug, title, sources.OUT, FILES)
    for _ in range(120):                                               # Kaggle unpacks the folders before it is ready
        s = subprocess.run(['kaggle', 'datasets', 'status', slug], capture_output=True, text=True).stdout.strip().lower()
        if s == 'ready': break
        time.sleep(30)
    else:
        sys.exit(f'{slug}: still "{s}" after an hour')
    local = tree(sources.OUT)
    with tempfile.TemporaryDirectory(dir=sources.DATA) as d:
        subprocess.run(['kaggle', 'datasets', 'download', slug, '-p', d, '--unzip', '-q'], check=True)
        got = tree(d) if all(os.path.exists(os.path.join(d, t)) for t in FILES) else {}
        bad = sorted(f for f in local if f not in got or sha(got[f]) != sha(local[f]))
    if bad: sys.exit(f'{slug}: {len(bad)} of {len(local)} files missing or different on Kaggle, e.g. {bad[:5]}')
    json.dump({'release': v, 'kaggle': f'https://www.kaggle.com/datasets/{slug}', 'files': len(local)},
              open(os.path.join(sources.OUT, 'kaggle-verified.json'), 'w'))
    print(json.dumps({'kaggle': f'https://www.kaggle.com/datasets/{slug}', 'verified_files': len(local)}))


if __name__ == '__main__':
    main()
