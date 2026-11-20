# GPPD-LD: the Global Power Plant Database as Linked Open Data

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.0000000.svg)](https://doi.org/10.5281/zenodo.0000000)
<!-- Replace 0000000 with the Zenodo record number after the v1.0 release is archived. -->

This repository turns the **WRI Global Power Plant Database v1.3.0** (one CSV
file, CC BY 4.0, a 3-star open dataset) into **5-star Linked Open Data**: RDF
that uses shared vocabularies, gives every plant a stable IRI and links to
other datasets (EU country authority table, Wikidata).

University project for *Seminars · Data Interoperability*, MEIC, FEUP, 2026/2027
(Group 2).

## What is in the output

| | |
|---|---|
| Power plants | 34,936 (in 167 countries); 9,578 with a checked `owl:sameAs` to Wikidata (9,520 US, 58 UK) |
| Organisations | 10,706 (15 with a checked `owl:sameAs` to Wikidata) |
| Reported generation observations (2013–2019) | 59,786 |
| Estimated generation observations (2013–2017) | 100,381 |
| Triples | 1,948,266 |
| SHACL violations | 0 |
| Issues logged | 443 (see [data/issues.csv](data/issues.csv)) |

For each plant, `data/output/gppd-ld.ttl` contains:

| CSV column | RDF |
|---|---|
| `gppd_idnr` | plant IRI `https://w3id.org/gppd-ld/plant/{gppd_idnr}` (`dbo:PowerStation`, `geo:Feature`, `oeo:OEO_00000031`) and `dcterms:identifier` |
| `name` | `dcterms:title` |
| `capacity_mw` | `dbo:installedCapacity` in **watts** (`xsd:double`, × 1,000,000) |
| `latitude`, `longitude` | `geo:hasGeometry` → `sf:Point` with `geo:asWKT "POINT(lon lat)"` |
| `primary_fuel`, `other_fuel1..3` | `dbo:primaryFuelType` / `dbo:otherFuelType` → concepts of `gppd:FuelScheme` |
| `commissioning_year` | `gppd:commissioningYear` (`xsd:decimal`, can be fractional) |
| `year_of_capacity_data` | `gppd:capacityDataYear` (`xsd:gYear`) |
| `country` | `dbo:country` → `http://publications.europa.eu/resource/authority/country/{ISO3}` |
| `owner`, `source`, `geolocation_source` | `prov:Organization` with `rdfs:label` (`owl:sameAs` Wikidata when the match is checked) |
| `url` | `prov:hadPrimarySource` |
| `wepp_id` | `adms:identifier` → `gppd:WEPPIdentifier` |
| `generation_gwh_2013..2019` | `qb:Observation` in `gppd:reportedGeneration` |
| `estimated_generation_gwh_2013..2017` + notes | `qb:Observation` in `gppd:estimatedGeneration` with `gppd:estimationMethod` |

The model is documented in [docs/EXE3-GPPD_LDAP.png](docs/EXE3-GPPD_LDAP.png)
(application profile) and checked by [shacl/gppd-shapes.ttl](shacl/gppd-shapes.ttl).

## Repository layout

```
pipeline/            Python pipeline, one module per stage
  ingest.py          1. read the CSV
  clean.py           2. deterministic cleaning; problems go to data/issues.csv
  link.py            3. countries -> EU authority table, organisations and plants -> Wikidata
  mapping.py         4. build the RDF graph (rdflib)
  validate.py        5. SHACL validation (pySHACL)
  publish.py         6. write Turtle (and a gzip copy)
ontology/gppd.ttl    minted terms, the two SKOS schemes (fuels linked to Wikidata), the Data Cube DSD
queries/             example SPARQL queries
shacl/               SHACL shapes (the application profile as machine-checkable rules)
data/raw/            WRI source CSV (+ WRI readme and release notes)
data/reference/      cached link tables (EU country codes, Wikidata matches)
data/issues.csv      issues log written by the pipeline
data/output/         gppd-ld.ttl.gz: the generated Linked Data, gzip-compressed (3.6 MB;
                     84 MB uncompressed, also attached to each GitHub release)
docs/                diagrams (draw.io + PNG)
```

## How to run

Requires Python 3.10+.

```bash
pip install -r requirements.txt

python -m pipeline --limit 200     # quick test: first 200 rows
python -m pipeline                 # full file (about 25 minutes, mostly SHACL validation)
```

To use the published data without running anything, unzip
`data/output/gppd-ld.ttl.gz` (e.g. `gzip -dk data/output/gppd-ld.ttl.gz`) or
download `gppd-ld.ttl` from the latest release.

Options:

| Option | What it does |
|---|---|
| `--limit N` | only convert the first N rows |
| `--wikidata N` | look up the N most frequent owners not yet in the Wikidata cache (default 0 = use the cache only, fully offline and reproducible) |
| `--refresh-countries` | download the EU country code list again |
| `--refresh-wikidata-plants` | download the Wikidata items with US (EIA) and UK (REPD) plant ids again |
| `--no-validate` | skip SHACL validation |

The pipeline stops with an error if the RDF does not pass the SHACL shapes,
and prints how many violations there are per rule.

### Source data

The CSV is included in `data/raw/` (12 MB). To download it again:
<https://wri-dataportal-prod.s3.amazonaws.com/manual/global_power_plant_database_v_1_3.zip>
(dataset page: <https://datasets.wri.org/dataset/globalpowerplantdatabase>).

## Example queries

The [queries/](queries/) folder has SPARQL queries to run against the data
(load `gppd-ld.ttl` and `ontology/gppd.ttl` into any SPARQL triple store):

| Query | What it shows |
|---|---|
| [01-capacity-by-fuel-in-country.rq](queries/01-capacity-by-fuel-in-country.rq) | installed capacity (GW) per fuel in Portugal, using the EU country IRI and the fuel scheme labels |
| [02-coal-capacity-by-country.rq](queries/02-coal-capacity-by-country.rq) | the ten countries with the most coal capacity |
| [03-reported-vs-estimated.rq](queries/03-reported-vs-estimated.rq) | plants whose WRI estimate is furthest from the reported generation, with the estimation model |
| [04-linked-plants-wikidata.rq](queries/04-linked-plants-wikidata.rq) | federated query: follows `owl:sameAs` into Wikidata to add each US nuclear plant's operator, which the GPPD does not contain |
| [05-links-and-provenance.rq](queries/05-links-and-provenance.rq) | how many observations each organisation supplied, per data set |

## Cleaning and linking rules

Only deterministic fixes are applied. Anything unusual is written to
[data/issues.csv](data/issues.csv) (`row_id, column, value, problem`) instead of being guessed:

- whitespace around values is removed;
- broken character encoding (e.g. `SvanemÃ¸lle` → `Svanemølle`) is repaired only when the reversal is exact;
- spaces and other characters not allowed in an IRI are percent-encoded (`" "` → `%20`); a cell holding two or more URLs is not used, because the profile allows one source document and choosing one would be a guess;
- several WEPP ids in one cell (`1074142| 1074143`) become several identifiers;
- an empty generation cell creates no observation; zero and negative values are real values and are kept;
- `NO-ESTIMATION` is not an estimation method;
- country `KOS` (Kosovo) is not an ISO code; it is mapped to the EU code `XKX` and logged;
- `owl:sameAs` to Wikidata is added only when three checks pass: the search returns exactly one item whose English label equals the organisation name exactly; that item is an organisation; and, if the item has a country, at least one of the owner's plants is in it. The last two checks reject false matches such as `IPP` (a human gene) or `CFE` (a Belgian railway company, while GPPD's CFE is Mexico's utility). All lookups, including rejections and their reason, are cached in `data/reference/wikidata-orgs.csv`; only the most frequent owners have been looked up so far (`--wikidata N` adds more).
- **US and UK plants** are linked to Wikidata (`owl:sameAs`) by identifier, not by name. For these two countries the GPPD id is a national registry code that Wikidata also stores: `USA` + the EIA plant code (property P10682) and `GBR` + the UK Renewable Energy Planning Database record number (property P9891). A link is added only if the code belongs to exactly one Wikidata item (and that item has only this code), the item is a power station, is in the right country, and its coordinates are within 5 km (US) or 10 km (UK, mostly wind farms spread over several kilometres) of the GPPD location. The ids of all other countries are WRI's own numbers, which Wikidata does not store, so those plants are not linked: matching by name would be a guess. This link goes beyond the application profile diagram, which does not forbid it; the shapes still pass. Decisions are in `data/reference/wikidata-plant-links.csv`; the Wikidata items are cached in `data/reference/wikidata-eia-plants.csv` and `wikidata-repd-plants.csv` (`--refresh-wikidata-plants` downloads them again).
- **Fuel concepts** are linked to Wikidata with `skos:closeMatch` (chosen by hand; `closeMatch` because the GPPD categories are broader, e.g. "Gas"). The estimation methods have no Wikidata items and point to WRI's technical note instead.

## Licence

- **Code** (pipeline, ontology, shapes): MIT, see [LICENSE](LICENSE).
- **Data** (source CSV and generated RDF): CC BY 4.0, derived from the WRI Global Power Plant Database v1.3.0.

> Global Energy Observatory, Google, KTH Royal Institute of Technology in
> Stockholm, Enipedia, World Resources Institute. 2019. Global Power Plant
> Database. Published on Resource Watch and Google Earth Engine.

## Authors

Group 2 · Tomás Macedo, Mara Almasan, Anabel Dautovic
