# world-gazetteer

A mirror of [PlaceDB](https://placedb.org) ([mindstellar/location-data](https://github.com/mindstellar/location-data), CC0,
built from Wikidata, CC0): every country, division and settlement, plus map files made from them. Checked weekly; a new
PlaceDB release is archived whole on Kaggle (`helenkwok/world-gazetteer-<release>`, one dataset per release), and only once
Kaggle lists that copy complete (every file, every size) are the map files on Hugging Face
([dataset](https://huggingface.co/datasets/alreadyopen/world-gazetteer), [bucket](https://huggingface.co/buckets/alreadyopen/world-gazetteer))
replaced. Built from [pipeline-template](https://github.com/AlreadyOpen/pipeline-template). The files are listed in
`hf/README.md`; PlaceDB's known gaps are in its [LIMITATIONS.md](https://github.com/mindstellar/location-data/blob/main/docs/LIMITATIONS.md).

    COUNTRIES=HK,TW,PT python3 bake.py   # a test on a few countries (near/ left out); no COUNTRIES = everything (CI)
    python3 archive.py                   # Kaggle: release.tar + api.tar + the top-level files; then Kaggle's file list must match
    python3 publish.py                   # gate, then Hugging Face (HF_TOKEN); refuses a test bake or an unverified release
    python3 check.py                     # data-free checks (CI)

How PlaceDB publishes a release: `geo.mindstellar.com/releases/latest.json` names it; `releases/<version>/manifest.json`
lists every country's `data/`, `json/` and `csv/` file with its sha256 and size; `api.placedb.org/v1/index.json` does the
same for the API's 143,197 files (`ac/`, `cities/`, `iso/`, `near/`, `regions/`). The bake refuses any file whose sha256
differs, and an API that is on a different release from the release files.

The publish gate compares the total of settlements, and each country that had at least 1,000 in the last release, with that
release, and stops on a drop of more than 10% (or such a country disappearing); smaller countries count in the total only; a manual run's **force** box overrides it, after a look at PlaceDB's `changes.ndjson`. A run whose release
is already on Hugging Face stops after one request.

Code: Apache-2.0. Data: CC0 (PlaceDB, Wikidata), see `sources.json`.
