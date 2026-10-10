"""Archive the whole release on Kaggle, one immutable dataset per PlaceDB release (helenkwok/world-gazetteer-<release>).
Kaggle gets few, plain files (never 143k small ones), staged in data/out/kaggle/:
  release.tar   PlaceDB's per-country data/<CC>.ndjson, json/<CC>.json, csv/<CC>.csv, as delivered (uncompressed tar)
  api.tar       the placedb.org API mirror as delivered: api/v1/index.json, countries.json, changes.json, ac/, cities/,
                iso/, near/, regions/ (uncompressed tar, so Kaggle keeps it as one file)
  manifest.json, latest.json, LICENSE, changes.json, changes.ndjson   PlaceDB's release files, as delivered
  LIMITATIONS.md and the derived files: places.parquet, divisions.parquet, places.pmtiles, index.json, releases.json
Kaggle unpacks the tars into folders (release/, api/). Once Kaggle says the dataset is ready, its file list (names and
sizes, never a download) must match the staged files and the tars' members exactly; only then does it write
kaggle-verified.json, which publish.py needs before it replaces the previous release on Hugging Face. A dataset that
already exists is never re-uploaded, versioned or deleted: if it matches, the run goes on to publish; if not, it stops. Needs KAGGLE_API_TOKEN in the environment (never on argv).
Usage: python3 archive.py     (after bake.py)"""
import json, os, shutil, subprocess, sys, tarfile, time
import kaggle_mirror, publish, sources

REL_FILES = ['manifest.json', 'latest.json', 'LICENSE', 'changes.json', 'changes.ndjson']
DERIVED = ['LIMITATIONS.md', 'places.parquet', 'divisions.parquet', 'places.pmtiles', 'index.json', 'releases.json']


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


def expected(k, files):
    """{path: bytes} as Kaggle lists the dataset: it unpacks a tar (even an uncompressed one; run 38055805774) into a
    folder named after it, so release.tar shows as release/data/HK.ndjson ..."""
    out = {}
    for f in files:
        if f.endswith('.tar'):
            with tarfile.open(os.path.join(k, f)) as tf:
                out.update({f'{f[:-4]}/{m.name}': m.size for m in tf if m.isfile()})
        else:
            out[f] = os.path.getsize(os.path.join(k, f))
    return out


def listed(slug):
    """every file of a Kaggle dataset with its size, page by page (200 a page); never downloads anything"""
    out, token = {}, None
    while True:
        r = kaggle('files', slug, '--csv', '--page-size', '200', *(['--page-token', token] if token else []), capture_output=True, text=True)
        if r.returncode != 0: return None
        token = None
        for line in r.stdout.splitlines():
            if line.startswith('Next Page Token = '): token = line.split(' = ', 1)[1].strip()
            elif line and not line.startswith('name,size'):
                name, size, _ = line.rsplit(',', 2); out[name] = int(size)
        if not token: return out


def ready(slug, minutes=20):
    for _ in range(minutes * 2):
        s = kaggle('status', slug, capture_output=True, text=True).stdout.strip().lower()
        if s == 'ready': return
        time.sleep(30)
    sys.exit(f'{slug}: still "{s}" after {minutes} minutes')


def main():
    idx, _ = publish.checked()                                         # the publish gate first: nothing is archived past it
    v = idx['release']; slug = f'helenkwok/world-gazetteer-{v.lower()}'; title = f'AlreadyOpen: world gazetteer {v}'
    k, files = stage(); want = expected(k, files)
    exists = kaggle('status', slug, capture_output=True).returncode == 0
    if not exists:
        kaggle_mirror.mirror(slug, title, k, files)
    ready(slug)
    got = listed(slug) or {}
    missing = sorted(f for f in want if f not in got); wrong = sorted(f for f in want if f in got and got[f] != want[f])
    extra = sorted(set(got) - set(want))
    if missing or wrong or extra:                                      # never deleted or versioned here: a person decides
        sys.exit(f'{slug} ({"existed" if exists else "new"}) does not match this release: {len(missing)} missing {missing[:5]}, '
                 f'{len(wrong)} of another size {wrong[:5]}, {len(extra)} unexpected {extra[:5]}')
    json.dump({'release': v, 'kaggle': f'https://www.kaggle.com/datasets/{slug}', 'files': len(want)},
              open(os.path.join(sources.OUT, 'kaggle-verified.json'), 'w'))
    print(json.dumps({'kaggle': f'https://www.kaggle.com/datasets/{slug}', 'existed': exists, 'verified_files': len(want)}))


if __name__ == '__main__':
    main()
