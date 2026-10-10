"""Mirror the current PlaceDB release (mindstellar/location-data, CC0, built from Wikidata) as delivered, every file checked
against its published sha256, and derive the map files from it. Every file, row and field is kept.
  release/   the release from geo.mindstellar.com/releases/<version>/: manifest.json (the checksum list), LICENSE,
             data/<CC>.ndjson, json/<CC>.json, csv/<CC>.csv, changes.json, changes.ndjson, and latest.json (the identifier)
  api/v1/    the placedb.org API files of the same release: index.json (their checksum list), countries.json, changes.json,
             regions/, cities/, iso/, near/, ac/ (the prefix files a browser search reads)
  LIMITATIONS.md   docs/LIMITATIONS.md from the repository at the release's tag
  places.parquet     GeoParquet, one point per settlement, every field
  divisions.parquet  GeoParquet, every administrative division (a point where it has coordinates), every field
  places.pmtiles     layer `places`, every settlement; the most populous from z2, everything by z10
  releases.json      every release published so far, with its Kaggle archive
index.json: built, release, s_version, counts {country code: settlements} (the publish gate compares these per country).
When the release is the one already published, nothing is downloaded and the run is skipped (GITHUB_OUTPUT skip=true).
Usage: python3 bake.py                     (COUNTRIES=HK,TW,PT for a test on a few countries; near/ is then left out)"""
import concurrent.futures, datetime, glob, hashlib, json, os, shutil, subprocess, sys, time, urllib.error, urllib.request
import duckdb
import manifest, sources

REL, API = 'https://geo.mindstellar.com/releases/', 'https://api.placedb.org/v1/'
DOCS = 'https://raw.githubusercontent.com/mindstellar/location-data/{}/docs/LIMITATIONS.md'
REPO = 'alreadyopen/world-gazetteer'
BUCKET = f'https://huggingface.co/buckets/{REPO}/resolve/'
ONLY = [c for c in os.environ.get('COUNTRIES', '').split(',') if c]
UA = {'User-Agent': 'AlreadyOpen world-gazetteer (https://github.com/AlreadyOpen/world-gazetteer)', 'Accept-Encoding': 'identity'}
# population -> first zoom: the biggest cities from z2, every settlement (and those with no population) by z10
ZOOMS = [(5_000_000, 2), (1_000_000, 3), (300_000, 4), (100_000, 5), (30_000, 6), (10_000, 7), (3_000, 8), (1_000, 9)]
MAXZOOM = 10


def get(url, tries=5):
    for t in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code < 500 or t == tries - 1: raise
        except OSError:
            if t == tries - 1: raise
        time.sleep(5 * (t + 1))


def sha(b):
    return hashlib.sha256(b).hexdigest()


def fetch(url, path, want=None):
    """download url to path unless it is already there with the right sha256; refuse a file whose sha256 differs"""
    if want and os.path.exists(path) and sha(open(path, 'rb').read()) == want:
        return
    b = get(url)
    if want and sha(b) != want:
        raise SystemExit(f'{url}: sha256 {sha(b)} is not the published {want}')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path + '.part', 'wb').write(b); os.replace(path + '.part', path)


def fetch_all(jobs):
    with concurrent.futures.ThreadPoolExecutor(16) as ex:
        for i, _ in enumerate(ex.map(lambda j: fetch(*j), jobs), 1):
            if i % 10000 == 0: print(f'  {i}/{len(jobs)}', file=sys.stderr)


def mine(path):
    """the API files of the test countries (a near/ cell holds several countries, so near/ is left out of a test)"""
    if not ONLY or '/' not in path: return True
    top, rest = path.split('/', 1)
    if top in ('ac', 'cities'): return rest.split('/')[0] in ONLY
    if top in ('regions', 'iso'): return rest.split('.')[0].split('-')[0] in ONLY + A3
    return False


def download(v):
    root = os.path.join(sources.CACHE, v); rel, api = os.path.join(root, 'release'), os.path.join(root, 'api', 'v1')
    man_b = get(f'{REL}{v}/manifest.json'); man = json.loads(man_b)
    os.makedirs(rel, exist_ok=True); open(os.path.join(rel, 'manifest.json'), 'wb').write(man_b)
    countries = [c for c in man['countries'] if not ONLY or c['code'] in ONLY]
    A3.extend(c.get('iso_3166_1_alpha3') or '' for c in json.loads(get(API + 'countries.json'))['countries'] if c['code'] in ONLY)
    jobs = [(f'{REL}{v}/{f}', os.path.join(rel, f)) for f in ['LICENSE', 'changes.json', 'changes.ndjson']]  # not in the manifest
    jobs += [(f'{REL}{v}/{c["files"][k]}', os.path.join(rel, c['files'][k]), c['sha256'][k]) for c in countries for k in c['files']]
    print(f'release {v}: {len(jobs)} files', file=sys.stderr); fetch_all(jobs)
    for c in countries:                                                # the manifest's byte counts too
        for k, f in c['files'].items():
            assert os.path.getsize(os.path.join(rel, f)) == c['bytes'][k], f'{f}: size differs from the manifest'
    idx_b = get(API + 'index.json'); idx = json.loads(idx_b)
    if idx['release'] != v:
        raise SystemExit(f'placedb.org API is on release {idx["release"]}, the release is {v}: not mixing them, rerun later')
    os.makedirs(api, exist_ok=True); open(os.path.join(api, 'index.json'), 'wb').write(idx_b)
    jobs = [(API + f, os.path.join(api, f), m['sha256']) for f, m in idx['files'].items() if mine(f)]
    print(f'api: {len(jobs)} of {len(idx["files"])} files', file=sys.stderr); fetch_all(jobs)
    open(os.path.join(rel, 'latest.json'), 'w').write(json.dumps(LATEST, indent=1))
    fetch(DOCS.format(v), os.path.join(root, 'LIMITATIONS.md'))
    return root, man, idx


def tile_ids(pmtiles, z):
    """distinct ids in zoom z of a tile set, read as a stream (a point near a tile edge also shows in the next tile's buffer)"""
    ids = set()
    p = subprocess.Popen(['tippecanoe-decode', '-z', str(z), '-Z', str(z), pmtiles], stdout=subprocess.PIPE, text=True)
    for line in p.stdout:
        line = line.strip().rstrip(',')
        if line.startswith('{ "type": "Feature"'):
            ids.add(json.loads(line)['properties']['id'])
    assert p.wait() == 0
    return ids


def derive(root):
    o = lambda f: os.path.join(sources.OUT, f)
    con = duckdb.connect(); con.execute('INSTALL spatial; LOAD spatial')
    # every country's records in one table; alt_names (language -> names) is read as a MAP so the column is the same in every
    # release, whatever languages appear
    con.execute(f"""CREATE TABLE r AS SELECT * FROM read_json('{root}/release/data/*.ndjson', format='newline_delimited',
        union_by_name=true, sample_size=-1, map_inference_threshold=0, filename=false)""")
    pt = 'ST_Point(TRY_CAST(longitude AS DOUBLE), TRY_CAST(latitude AS DOUBLE))'
    for t, kind in [('places', 'settlement'), ('divisions', 'region')]:
        # exactly the keys this record type carries (null or not), in the order of the table, and not the other types' keys
        keys = {k for k, in con.execute(f"""SELECT DISTINCT unnest(json_keys(json)) FROM read_ndjson_objects('{root}/release/data/*.ndjson')
            WHERE json->>'type' = '{kind}'""").fetchall()} - {'type'}
        cols = [c for c, in con.execute('SELECT column_name FROM (DESCRIBE r)').fetchall() if c in keys]
        con.execute(f"""CREATE TABLE {t} AS SELECT {', '.join(f'"{c}"' for c in cols)}, CASE WHEN TRY_CAST(longitude AS DOUBLE) IS NOT NULL AND TRY_CAST(latitude AS DOUBLE) IS NOT NULL THEN {pt} END AS geometry
            FROM r WHERE type = '{kind}'""")
        con.execute(f"COPY {t} TO '{o(t + '.parquet')}' (FORMAT parquet, COMPRESSION zstd)")
    other = con.execute("SELECT list(DISTINCT type) FROM r WHERE type NOT IN ('settlement', 'region', 'country')").fetchone()[0]
    assert not other, f'record types this bake does not handle: {other}'
    nogeo = con.execute('SELECT count(*) FROM places WHERE geometry IS NULL').fetchone()[0]
    assert not nogeo, f'{nogeo} settlements have no coordinates'
    counts = dict(con.execute('SELECT country_code, count(*) FROM places GROUP BY 1 ORDER BY 1').fetchall())

    # tiles: Web Mercator stops at 85.0511 degrees, so a place nearer a pole sits at that latitude (its true latitude is a field)
    zoom = 'CASE ' + ' '.join(f'WHEN population >= {p} THEN {z}' for p, z in ZOOMS) + f' ELSE {MAXZOOM} END'
    tmp = os.path.join(sources.DATA, 'tmp'); os.makedirs(tmp, exist_ok=True); gj = os.path.join(tmp, 'places.geojsonl')
    con.execute(f"""COPY (WITH q AS (SELECT * EXCLUDE (geometry) FROM places)
        SELECT 'Feature' AS type, ST_AsGeoJSON(ST_Point(longitude::DOUBLE, greatest(least(latitude::DOUBLE, 85.0511), -85.0511)))::JSON AS geometry,
            q AS properties, {{'minzoom': {zoom}}} AS tippecanoe FROM q ORDER BY population DESC NULLS LAST)
        TO '{gj}' (FORMAT json)""")
    subprocess.run(['tippecanoe', '-o', o('places.pmtiles'), '--force', '-l', 'places', '-Z2', f'-z{MAXZOOM}', '-r1',
                    '--no-feature-limit', '--no-tile-size-limit', '--quiet', gj], check=True)
    shutil.rmtree(tmp)
    want = {i for i, in con.execute('SELECT DISTINCT id FROM places').fetchall()}
    got = tile_ids(o('places.pmtiles'), MAXZOOM)
    assert got == want, f'places.pmtiles z{MAXZOOM}: {len(want - got)} places missing, {len(got - want)} unexpected'
    return counts, {'places': con.execute('SELECT count(*) FROM places').fetchone()[0], 'places_distinct_ids': len(want),
                    'places_tiles_deepest_zoom': len(got), 'divisions': con.execute('SELECT count(*) FROM divisions').fetchone()[0]}


A3, LATEST = [], {}


def main():
    LATEST.update(json.loads(get(REL + 'latest.json'))); v = LATEST['version']
    old = manifest.published(BUCKET + 'index.json')
    if old and old.get('release') == v and os.environ.get('BAKE_FORCE') != '1' and not ONLY:
        print(json.dumps({'checked': datetime.datetime.now().isoformat(timespec='seconds'), 'release': v, 'skipped': 'already published'}))
        if os.environ.get('GITHUB_OUTPUT'): open(os.environ['GITHUB_OUTPUT'], 'a').write('skip=true\n')
        return
    root, man, idx = download(v)
    os.makedirs(sources.OUT, exist_ok=True)
    for f in ['release', 'api', 'LIMITATIONS.md']:                      # the mirror, as delivered, beside the derived files
        p = os.path.join(sources.OUT, f)
        if os.path.lexists(p): os.remove(p)
        os.symlink(os.path.join(root, f), p)
    counts, totals = derive(root)
    built = datetime.datetime.now().isoformat(timespec='seconds')
    entry = {'release': v, 'released': LATEST['released'], 's_version': LATEST['s_version'], 'built': built,
             'kaggle': f'https://www.kaggle.com/datasets/helenkwok/world-gazetteer-{v.lower()}', **totals}
    releases = [r for r in ((manifest.published(BUCKET + 'releases.json') or {}).get('releases') or []) if r['release'] != v]
    json.dump({'releases': releases + [entry]}, open(os.path.join(sources.OUT, 'releases.json'), 'w'), indent=1)
    out = {'built': built, 'release': v, 's_version': LATEST['s_version'], 'test_countries': ONLY or None,
           'counts': counts, 'totals': totals}
    json.dump(out, open(os.path.join(sources.OUT, 'index.json'), 'w'), indent=1)
    print(json.dumps({k: out[k] for k in ('release', 'totals')}))


if __name__ == '__main__':
    main()
