"""Publish the latest PlaceDB release's map files to Hugging Face (needs HF_TOKEN with write access to the alreadyopen org),
after archive.py has put the whole release on Kaggle and verified it (Helen: Kaggle holds the archive, HF only what the map
needs):
  dataset  REPO  DATASET_FILES + manifest.json + the card (hf/README.md): the index of releases, versioned
  bucket   REPO  BUCKET_FILES + the prefix files (api/v1/ac/, checked by api/v1/index.json) + manifest.json, replaced in place;
                 the previous release's prefix files that the new one no longer has are deleted
Nothing is uploaded unless the publish gate passes (manifest.py: settlements per country, a drop > 10% stops it).
Usage: python3 publish.py     (after bake.py and archive.py)"""
import json, os, sys
from huggingface_hub import HfApi, batch_bucket_files, create_bucket
import manifest, sources

REPO = 'alreadyopen/world-gazetteer'
DATASET_FILES = ['index.json', 'releases.json']
BUCKET_FILES = ['index.json', 'releases.json', 'places.pmtiles', 'places.parquet', 'divisions.parquet', 'api/v1/countries.json',
                'api/v1/index.json', 'LIMITATIONS.md']
KAGGLE = ('helenkwok/world-gazetteer', 'AlreadyOpen: world gazetteer')   # the index of releases; archive.py makes one per release
BUCKET = f'https://huggingface.co/buckets/{REPO}/resolve/'
o = lambda f: os.path.join(sources.OUT, f)


def checked():
    """index.json and the new manifest, once the publish gate has passed"""
    idx = json.load(open(o('index.json')))
    if idx.get('test_countries'): sys.exit(f'a test bake ({idx["test_countries"]}): not publishing')
    m = manifest.manifest(sources.OUT, sorted(set(DATASET_FILES + BUCKET_FILES)), idx['counts'], idx['built'])
    manifest.gate(m, BUCKET + 'manifest.json')
    return idx, m


def ac_files(index):
    return {f for f in (index or {}).get('files', {}) if f.startswith('ac/')}


def main():
    idx, m = checked()
    done = json.load(open(o('kaggle-verified.json'))) if os.path.exists(o('kaggle-verified.json')) else {}
    if done.get('release') != idx['release']: sys.exit(f'release {idx["release"]} is not verified on Kaggle yet (archive.py): not replacing HF')
    json.dump(m, open(o('manifest.json'), 'w'), indent=1)
    api = HfApi(); api.create_repo(REPO, repo_type='dataset', exist_ok=True)
    for f in DATASET_FILES + ['manifest.json']:
        api.upload_file(path_or_fileobj=o(f), path_in_repo=f, repo_id=REPO, repo_type='dataset', commit_message=f"{f}: release {idx['release']}")
    api.upload_file(path_or_fileobj=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hf', 'README.md'), path_in_repo='README.md', repo_id=REPO, repo_type='dataset', commit_message='card')
    old = ac_files(manifest.published(BUCKET + 'api/v1/index.json')); new = ac_files(json.load(open(o('api/v1/index.json'))))
    create_bucket(REPO, private=False, exist_ok=True)
    batch_bucket_files(REPO, add=[(o(f), f) for f in BUCKET_FILES] + [(o('api/v1/' + f), 'api/v1/' + f) for f in sorted(new)],
                       delete=['api/v1/' + f for f in sorted(old - new)])
    batch_bucket_files(REPO, add=[(o('manifest.json'), 'manifest.json')])   # last: the gate and the next bake read it
    print(json.dumps({'dataset': f'https://huggingface.co/datasets/{REPO}', 'bucket': f'https://huggingface.co/buckets/{REPO}',
                      'release': idx['release'], 'kaggle': done['kaggle'], 'prefix_files': len(new), 'deleted': len(old - new),
                      'totals': idx['totals']}))


if __name__ == '__main__':
    main()
