"""Command line entry point:  python -m pipeline [options]

Examples
    python -m pipeline --limit 200          # quick test on the first 200 rows
    python -m pipeline                      # full file
    python -m pipeline --wikidata 200       # also look up the 200 most frequent owners
    python -m pipeline --upload             # also upload to Fuseki (env variables)
"""

import argparse
import sys
import time

from . import config
from .clean import clean
from .ingest import ingest
from .issues import IssueLog
from .link import (link_countries, link_organisations, link_plants_wikidata,
                   refresh_eu_countries)
from .mapping import build_graph
from .publish import upload_to_fuseki, write_turtle
from .validate import validate


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m pipeline", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, help="only convert the first N rows of the CSV")
    ap.add_argument("--wikidata", type=int, default=0, metavar="N",
                    help="look up the N most frequent uncached owners on Wikidata (default 0: cache only)")
    ap.add_argument("--refresh-countries", action="store_true",
                    help="download the EU country code list again")
    ap.add_argument("--refresh-wikidata-plants", action="store_true",
                    help="download the Wikidata items with an EIA plant id again")
    ap.add_argument("--no-validate", action="store_true", help="skip SHACL validation")
    ap.add_argument("--upload", action="store_true", help="upload the result to Fuseki")
    ap.add_argument("--upload-only", action="store_true",
                    help="upload the existing data/output/gppd-ld.ttl without converting again")
    args = ap.parse_args(argv)
    t0 = time.time()

    if args.upload_only:
        if not config.OUTPUT_TTL.exists():
            raise SystemExit("No output yet: run python -m pipeline first.")
        print("6. publish (upload only)")
        upload_to_fuseki()
        return 0
    log = IssueLog()

    print("1. ingest")
    df = ingest(args.limit)
    print(f"  {len(df):,} rows read")

    print("2. clean")
    plants = clean(df, log)
    print(f"  {len(plants):,} plants kept")

    print("3. link")
    if args.refresh_countries or not config.EU_COUNTRIES_CSV.exists():
        refresh_eu_countries()
    plants = link_countries(plants, log)
    orgs = link_organisations(plants, args.wikidata)
    n_same = sum(1 for _, qid in orgs.values() if qid)
    print(f"  {len(plants):,} plants with a country, {len(orgs):,} organisations, "
          f"{n_same} linked to Wikidata")
    outcome, rejections = link_plants_wikidata(plants, args.refresh_wikidata_plants)
    for registry, counts in outcome.items():
        print(f"  plants -> Wikidata via {registry} code: {counts.get('checked', 0):,} linked, "
              f"{counts.get('rejected', 0):,} candidates rejected")
    print(f"  (decisions in {config.WIKIDATA_PLANT_LINKS_CSV.relative_to(config.ROOT)})")
    for reason, n in rejections.most_common():
        print(f"    {n:>6}  {reason}")

    log.write(config.ISSUES_CSV)
    print(f"  {len(log.rows):,} issues logged in {config.ISSUES_CSV.relative_to(config.ROOT)}")
    for problem, n in log.summary():
        print(f"    {n:>6}  {problem}")

    print("4. map to RDF")
    graph = build_graph(plants, orgs)
    print(f"  {len(graph):,} triples")

    if not args.no_validate:
        print("5. validate")
        ok, _ = validate(graph)
        if not ok:
            print("FAILED: the output does not conform to shacl/gppd-shapes.ttl", file=sys.stderr)
            return 1

    print("6. publish")
    write_turtle(graph)
    if args.upload:
        upload_to_fuseki()

    print(f"done in {time.time() - t0:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
