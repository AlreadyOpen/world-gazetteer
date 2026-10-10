"""Archive the whole release on Kaggle, one immutable dataset per PlaceDB release (helenkwok/world-gazetteer-<release>).
Kaggle gets few, plain files (never 143k small ones), staged in data/out/kaggle/:
  release.tar   PlaceDB's per-country data/<CC>.ndjson, json/<CC>.json, csv/<CC>.csv, as delivered (uncompressed tar)
  api.tar       the placedb.org API mirror as delivered: api/v1/index.json, countries.json, changes.json, ac/, cities/,
                iso/, near/, regions/ (uncompressed tar, so Kaggle keeps it as one file)
  manifest.json, latest.json, LICENSE, changes.json, changes.ndjson   PlaceDB's release files, as delivered
  LIMITATIONS.md and the derived files: places.parquet, divisions.parquet, places.pmtiles, index.json, releases.json
Then it downloads the dataset back and checks every file's sha256 against the staged copy; only then does it write
kaggle-verified.json, which publish.py needs before it replaces the previous release on Hugging Face. A dataset that
already exists is never versioned, only verified again. Needs KAGGLE_API_TOKEN in the environment (never on argv).
Usage: python3 archive.py     (after bake.py)"""
import hashlib, json, os, shutil, subprocess, sys, tarfile, tempfile, time
import kaggle_mirror, publish, sources

REL_FILES = ['manifest.json', 'latest.json', 'LICENSE', 'changes.json', 'changes.ndjson']
DERIVED = ['LIMITATIONS.md', 'places.parquet', 'divisions.parquet', 'places.pmtiles', 'index.json', 'releases.json']


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
    return h.hexdigest()


def tar(out, base, tops):
    """an uncompressed tar of base/<top>, entries sorted, owner and times fixed (the same input gives the same bytes)"""
    def norm(t):
        t.uid = t.gid = 0; t.uname = t.gname = ''; t.mtime = 0; return t
    with tarfile.open(out, 'w', format=tarfile.PAX_FORMAT) as tf:
        for top in tops:
            for d, ds, fs in sorted(os.walk(os.path.join(base, top), followlinks=True)):
                ds.sort()
                for f in sorted(fs):
                    p = os.path.join(d, f); tf.add(p, os.path.relpath(p, base), recursive=False, filter=norm)


def stage():
    k = os.path.join(sources.OUT, 'kaggle'); shutil.rmtree(k, ignore_errors=True); os.makedirs(k)
    rel = os.path.realpath(os.path.join(sources.OUT, 'release'))
    tar(os.path.join(k, 'release.tar'), rel, [d for d in ('data', 'json', 'csv') if os.path.isdir(os.path.join(rel, d))])
    tar(os.path.join(k, 'api.tar'), os.path.realpath(os.path.join(sources.OUT, 'api', '..')), ['api'])
    for f in REL_FILES: os.link(os.path.join(rel, f), os.path.join(k, f))
    for f in DERIVED: os.link(os.path.realpath(os.path.join(sources.OUT, f)), os.path.join(k, f))
    return k, sorted(os.listdir(k))


def kaggle(*a, **kw):
    return subprocess.run(['kaggle', 'datasets', *a], **kw)


def main():
    idx, _ = publish.checked()                                         # the publish gate first: nothing is archived past it
    v = idx['release']; slug = f'helenkwok/world-gazetteer-{v.lower()}'; title = f'AlreadyOpen: world gazetteer {v}'
    k, files = stage()
    if kaggle('files', slug, capture_output=True).returncode != 0:
        kaggle_mirror.mirror(slug, title, k, files)
    for _ in range(120):                                               # Kaggle processes an upload before it is ready
        s = kaggle('status', slug, capture_output=True, text=True).stdout.strip().lower()
        if s == 'ready': break
        time.sleep(30)
    else:
        sys.exit(f'{slug}: still "{s}" after an hour')
    with tempfile.TemporaryDirectory(dir=sources.DATA) as d:
        kaggle('download', slug, '-p', d, '--unzip', '-q', check=True)
        bad = [f for f in files if not os.path.isfile(os.path.join(d, f)) or sha(os.path.join(d, f)) != sha(os.path.join(k, f))]
        extra = sorted(set(os.listdir(d)) - set(files))
    if bad or extra: sys.exit(f'{slug}: on Kaggle, missing or different: {bad}; unexpected: {extra}')
    json.dump({'release': v, 'kaggle': f'https://www.kaggle.com/datasets/{slug}', 'files': files},
              open(os.path.join(sources.OUT, 'kaggle-verified.json'), 'w'))
    print(json.dumps({'kaggle': f'https://www.kaggle.com/datasets/{slug}', 'verified': files}))


if __name__ == '__main__':
    main()
