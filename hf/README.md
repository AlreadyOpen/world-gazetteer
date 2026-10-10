---
pretty_name: World gazetteer (PlaceDB)
license: cc0-1.0
license_link: https://creativecommons.org/publicdomain/zero/1.0/
tags:
  - geospatial
  - gazetteer
  - places
---

# World gazetteer

Every country, administrative division and settlement in [PlaceDB](https://placedb.org), the CC0 gazetteer built from
Wikidata by [mindstellar/location-data](https://github.com/mindstellar/location-data), mirrored by
[AlreadyOpen/world-gazetteer](https://github.com/AlreadyOpen/world-gazetteer). It is checked weekly and copied when a new
PlaceDB release appears. Every file, row and field is kept.

**Where things are.** The archive is on Kaggle: one dataset per PlaceDB release, `helenkwok/world-gazetteer-<release>`,
holding the release exactly as delivered plus the files below, every file checked against PlaceDB's own sha256 list. The
small Kaggle dataset `helenkwok/world-gazetteer` and `releases.json` list every release and its archive. Hugging Face holds
only what a map needs, for the latest release:

| File | Holds |
|---|---|
| `places.parquet` | GeoParquet, one point per settlement, every field PlaceDB gives a settlement |
| `divisions.parquet` | GeoParquet, every administrative division (a point where it has coordinates), every field |
| `places.pmtiles` | Vector tiles, layer `places`, every settlement. Cities of 5 million or more from zoom 2, then by population down to zoom 10, where every settlement is present (also those with no population) |
| `api/v1/countries.json` | PlaceDB's country list, as published |
| `api/v1/ac/<CC>/<prefix>.json` | PlaceDB's prefix files for search as you type, as published; `api/v1/index.json` holds their sha256 |
| `LIMITATIONS.md` | PlaceDB's own account of what the dataset does not do, at this release |
| `index.json`, `releases.json` | This release's settlements per country (`per_country`) and the counts the publish gate checks; every release published so far |

The Kaggle archive of a release holds PlaceDB's own files as delivered. They are uploaded as two tars, which Kaggle shows
unpacked as the folders `release/` and `api/`; downloading the dataset gives them back as folders.

| File | Holds |
|---|---|
| `release.tar` | `data/<CC>.ndjson`, `json/<CC>.json`, `csv/<CC>.csv` for every country (an uncompressed tar) |
| `api.tar` | the placedb.org API files: `api/v1/index.json` (their sha256), `countries.json`, `changes.json`, `ac/`, `cities/`, `iso/`, `near/`, `regions/` (an uncompressed tar of about 143,000 files) |
| `manifest.json` | PlaceDB's checksum list: every per-country file's sha256 and size |
| `latest.json`, `LICENSE`, `changes.json`, `changes.ndjson` | the release's name and date, its CC0 licence, and what changed since the release before |

plus `LIMITATIONS.md` and the derived files above. If you have a tar rather than the folder, extract it with
`tar -xf release.tar` (or `tar -xf api.tar`). Then check the files against `manifest.json` (or `api/v1/index.json`), for example from inside `release/`:
`python3 -c "import hashlib,json;m=json.load(open('../manifest.json'));print(all(hashlib.sha256(open(c['files'][k],'rb').read()).hexdigest()==c['sha256'][k] for c in m['countries'] for k in c['files']))"`.

In the tiles, a place nearer a pole than 85.05 degrees sits at that latitude, since web maps stop there; its true
`latitude` and `longitude` are fields.

## Known gaps

From PlaceDB's [LIMITATIONS.md](https://github.com/mindstellar/location-data/blob/main/docs/LIMITATIONS.md), which is worth
reading before using the data:

- **Settlements with no coordinates are left out**: about 883,000 of them, two thirds China's administrative villages, most
  of the rest in India, Russia, Uganda and Myanmar.
- **Names in Arabic script are not transliterated**, so about 164,000 settlements whose only names are in Arabic (or
  Hebrew) script have no usable name and are left out. Cyrillic, Greek, Georgian, Armenian and Chinese are transliterated.
- **Vietnam is undercounted**: Wikidata files many of its towns under "former subdivisions of Vietnam".

## Sources and terms

Data from **PlaceDB (mindstellar/location-data), CC0, built from Wikidata (CC0)**: [placedb.org](https://placedb.org),
[github.com/mindstellar/location-data](https://github.com/mindstellar/location-data), released under
[CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/); [Wikidata](https://www.wikidata.org/) is also CC0. Only
PlaceDB's published data is copied here, not its code (which is GPL-3.0). Provided as is, with no warranty, not endorsed by
PlaceDB or Wikidata. A wrong place is best fixed in its Wikidata item.
