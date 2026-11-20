"""Stage 3 - Link: connect our data to existing Linked Data.

* Countries -> EU Publications Office country authority table.
  The list of valid codes is cached in data/reference/eu-countries.csv
  (refresh it with --refresh-countries).
* Organisations -> Wikidata, owl:sameAs only for *checked* matches. A name is
  linked only if all three checks pass:
    1. the Wikidata search finds exactly one item whose English label is
       exactly the organisation name (disambiguation pages ignored);
    2. that item is an organisation (instance of a subclass of Q43229);
    3. if the item has a country, at least one plant of this owner is in it.
  Checks 2 and 3 stop false links such as "IPP" -> a human gene, or
  "CFE" (Mexico's electricity utility) -> a Belgian railway company.
  Every answer, including rejections and their reason, is cached in
  data/reference/wikidata-orgs.csv, so the pipeline is reproducible and the
  API is asked about each name only once.
* Every organisation name gets one stable IRI under https://w3id.org/gppd-ld/org/.
"""

import csv
import hashlib
import math
import re
import time
import unicodedata
from collections import Counter, defaultdict

import requests

from . import config

# --------------------------------------------------------------------------
# Countries
# --------------------------------------------------------------------------

EU_SPARQL = "https://publications.europa.eu/webapi/rdf/sparql"


def refresh_eu_countries():
    """Download the code list from the EU SPARQL endpoint into the cache file."""
    query = ("SELECT DISTINCT ?c WHERE { ?c <http://www.w3.org/2004/02/skos/core#inScheme> "
             "<http://publications.europa.eu/resource/authority/country> }")
    resp = requests.get(EU_SPARQL, params={"query": query},
                        headers={"Accept": "text/csv", "User-Agent": config.USER_AGENT},
                        timeout=60)
    resp.raise_for_status()
    codes = set()
    for line in resp.text.splitlines()[1:]:
        code = line.strip().strip('"').rsplit("/", 1)[-1]
        if re.fullmatch(r"[A-Z]{3}", code):
            codes.add(code)
    config.EU_COUNTRIES_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(config.EU_COUNTRIES_CSV, "w", newline="", encoding="utf-8") as f:
        f.write("code\n" + "\n".join(sorted(codes)) + "\n")
    print(f"  saved {len(codes)} EU country codes")


def load_eu_countries():
    with open(config.EU_COUNTRIES_CSV, encoding="utf-8") as f:
        return {row["code"] for row in csv.DictReader(f)}


def link_countries(plants, log):
    """Set plant['country_iri']; drop plants whose code has no match."""
    valid = load_eu_countries()
    kept = []
    for p in plants:
        code = p["country"]
        if code in config.COUNTRY_ALIASES:
            new = config.COUNTRY_ALIASES[code]
            log.add(p["id"], "country", code,
                    f"not an ISO alpha-3 code; mapped to EU authority code {new}")
            code = new
        if code not in valid:
            log.add(p["id"], "country", code,
                    "no match in EU country authority table; plant dropped")
            continue
        p["country_code"] = code
        p["country_iri"] = config.COUNTRY[code]
        kept.append(p)
    return kept


# --------------------------------------------------------------------------
# Organisation IRIs
# --------------------------------------------------------------------------

def _slug(label):
    text = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode()
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return text[:60].strip("-") or "org"


def organisation_iris(labels):
    """Give each distinct organisation name one IRI.

    The IRI is a readable slug of the name. When two different names give the
    same slug (e.g. "ABC Ltd" and "ABC, Ltd."), both get a short hash of the
    exact name appended, so the result does not depend on processing order.
    """
    labels = set(labels)
    fixed = {config.WRI_LABEL: config.WRI, config.GROUP_LABEL: config.GROUP}
    slugs = {lab: _slug(lab) for lab in labels if lab not in fixed}
    counts = Counter(slugs.values())
    reserved = {"wri", "group2"}
    iris = {lab: iri for lab, iri in fixed.items() if lab in labels}
    for lab, s in slugs.items():
        if counts[s] > 1 or s in reserved:
            s = f"{s}-{hashlib.sha1(lab.encode('utf-8')).hexdigest()[:8]}"
        iris[lab] = config.ORG[s]
    return iris


# --------------------------------------------------------------------------
# Wikidata
# --------------------------------------------------------------------------

CACHE_FIELDS = ["label", "candidate_id", "wikidata_id", "result"]
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
UNCHECKED = "exact label match; not verified yet"


def load_wikidata_cache():
    cache = {}
    if config.WIKIDATA_CACHE_CSV.exists():
        with open(config.WIKIDATA_CACHE_CSV, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                if "candidate_id" not in row:  # older cache format
                    row["candidate_id"] = row.get("wikidata_id", "")
                    row["wikidata_id"] = ""
                    if row["candidate_id"]:
                        row["result"] = UNCHECKED
                cache[row["label"]] = {k: row.get(k, "") for k in CACHE_FIELDS}
    return cache


def save_wikidata_cache(cache):
    config.WIKIDATA_CACHE_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(config.WIKIDATA_CACHE_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CACHE_FIELDS)
        w.writeheader()
        for label in sorted(cache):
            w.writerow(cache[label])


def _get(session, url, params):
    """GET with polite retries when Wikidata says "too many requests"."""
    for attempt in range(5):
        resp = session.get(url, params=params, timeout=120)
        if resp.status_code != 429:
            break
        time.sleep(int(resp.headers.get("Retry-After", 10 * (attempt + 1))))
    resp.raise_for_status()
    return resp.json()


def search_label(label, session):
    """Check 1. Return (candidate qid or "", result note)."""
    data = _get(session, config.WIKIDATA_API, {
        "action": "wbsearchentities", "search": label, "language": "en",
        "type": "item", "limit": 20, "format": "json"})
    hits = [h for h in data.get("search", [])
            if h.get("match", {}).get("type") == "label"
            and h.get("label") == label
            and "disambiguation" not in (h.get("description") or "").lower()]
    if len(hits) == 1:
        return hits[0]["id"], UNCHECKED
    if not hits:
        return "", "no exact label match"
    return "", f"ambiguous: {len(hits)} items with this exact label"


def verify_candidates(cache, owner_countries, session):
    """Checks 2 and 3 for every candidate not verified yet (one SPARQL query per 100)."""
    todo = [row for row in cache.values() if row["result"] == UNCHECKED]
    for start in range(0, len(todo), 100):
        batch = todo[start:start + 100]
        values = " ".join(f"wd:{row['candidate_id']}" for row in batch)
        query = f"""
            SELECT ?item ?isOrg (GROUP_CONCAT(DISTINCT ?iso; separator=" ") AS ?countries) WHERE {{
              VALUES ?item {{ {values} }}
              BIND (EXISTS {{ ?item wdt:P31/wdt:P279* wd:Q43229 }} AS ?isOrg)
              OPTIONAL {{ ?item wdt:P17/wdt:P298 ?iso }}
            }} GROUP BY ?item ?isOrg"""
        data = _get(session, WIKIDATA_SPARQL, {"query": query, "format": "json"})
        facts = {}
        for b in data["results"]["bindings"]:
            qid = b["item"]["value"].rsplit("/", 1)[-1]
            facts[qid] = (b["isOrg"]["value"] == "true",
                          set(b.get("countries", {}).get("value", "").split()))
        for row in batch:
            is_org, countries = facts.get(row["candidate_id"], (False, set()))
            plant_countries = owner_countries.get(row["label"], set())
            if not is_org:
                row["result"] = "rejected: Wikidata item is not an organisation"
            elif countries and plant_countries and not countries & plant_countries:
                row["result"] = (f"rejected: item country {'/'.join(sorted(countries))} "
                                 f"but plants in {'/'.join(sorted(plant_countries))}")
            else:
                row["wikidata_id"] = row["candidate_id"]
                row["result"] = "checked: exact label, organisation, country fits"
        time.sleep(1.0)


def update_wikidata_cache(owners, owner_countries, top_n):
    """Search the `top_n` most frequent uncached owners, then verify candidates."""
    cache = load_wikidata_cache()
    todo = [lab for lab, _ in owners.most_common() if lab not in cache]
    if config.WRI_LABEL not in cache:
        todo.insert(0, config.WRI_LABEL)
    todo = todo[:top_n]

    session = requests.Session()
    session.headers["User-Agent"] = config.USER_AGENT
    if todo:
        print(f"  asking Wikidata about {len(todo)} organisation names ...")
    for i, label in enumerate(todo, 1):
        try:
            qid, note = search_label(label, session)
        except requests.RequestException as e:
            print(f"  stopped after {i - 1}: {e}")
            break
        cache[label] = {"label": label, "candidate_id": qid, "wikidata_id": "", "result": note}
        if i % 25 == 0:
            save_wikidata_cache(cache)  # keep progress if interrupted
            print(f"    {i}/{len(todo)}")
        time.sleep(1.0)  # be polite to the public API

    try:
        verify_candidates(cache, owner_countries, session)
    except requests.RequestException as e:
        print(f"  verification stopped: {e}")
    save_wikidata_cache(cache)
    return cache


# --------------------------------------------------------------------------
# Plants -> Wikidata, through national plant registry identifiers
# --------------------------------------------------------------------------
# For two countries the GPPD id is a national registry code that Wikidata also
# stores, so these plants can be linked by an exact identifier match instead
# of by name:
#   USA0063292 -> EIA-860 plant code 63292     (Wikidata property P10682)
#   GBR0004331 -> UK REPD record number 4331   (Wikidata property P9891)
# The ids of all other countries are WRI's own numbers, which Wikidata does
# not store. Wikidata itself contains mistakes, so a link is added only if all
# checks pass:
#   1. the code belongs to exactly one Wikidata item, and that item has only
#      this one code (otherwise several plants would be "the same");
#   2. the item is a power station (instance of a subclass of Q159719);
#   3. the item's country, if it has one, is the plant's country;
#   4. the item's coordinates are within max_km of the GPPD location
#      (a little more in the UK, where most matches are wind farms that are
#      spread over several kilometres).

PLANT_REGISTRIES = [
    {"prefix": "USA", "name": "EIA", "property": "P10682", "country": "Q30",
     "country_name": "the USA", "max_km": 5.0, "cache": config.WIKIDATA_EIA_CSV},
    {"prefix": "GBR", "name": "REPD", "property": "P9891", "country": "Q145",
     "country_name": "the UK", "max_km": 10.0, "cache": config.WIKIDATA_REPD_CSV},
]
ITEM_FIELDS = ["qid", "code", "label", "is_power_station", "countries", "coordinates"]


def refresh_wikidata_registry(reg):
    """Download every Wikidata item with this registry's id into its cache file."""
    query = f"""
        SELECT ?item ?id ?label ?country ?coord ?isPS WHERE {{
          ?item wdt:{reg["property"]} ?id .
          OPTIONAL {{ ?item rdfs:label ?label FILTER(LANG(?label) = "en") }}
          OPTIONAL {{ ?item wdt:P17 ?country }}
          OPTIONAL {{ ?item wdt:P625 ?coord }}
          BIND (EXISTS {{ ?item wdt:P31/wdt:P279* wd:Q159719 }} AS ?isPS)
        }}"""
    session = requests.Session()
    session.headers["User-Agent"] = config.USER_AGENT
    data = _get(session, WIKIDATA_SPARQL, {"query": query, "format": "json"})
    items = {}
    for b in data["results"]["bindings"]:
        qid = b["item"]["value"].rsplit("/", 1)[-1]
        it = items.setdefault(qid, {"qid": qid, "code": set(), "label": "",
                                    "is_power_station": "", "countries": set(),
                                    "coordinates": set()})
        it["code"].add(b["id"]["value"].strip().lstrip("0") or "0")
        it["label"] = it["label"] or b.get("label", {}).get("value", "")
        it["is_power_station"] = b["isPS"]["value"]
        if "country" in b:
            it["countries"].add(b["country"]["value"].rsplit("/", 1)[-1])
        if "coord" in b:
            it["coordinates"].add(b["coord"]["value"])
    reg["cache"].parent.mkdir(parents=True, exist_ok=True)
    with open(reg["cache"], "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ITEM_FIELDS)
        w.writeheader()
        for qid in sorted(items, key=lambda q: int(q[1:])):
            it = items[qid]
            w.writerow({**it, "code": " ".join(sorted(it["code"])),
                        "countries": " ".join(sorted(it["countries"])),
                        "coordinates": ";".join(sorted(it["coordinates"]))})
    print(f"  saved {len(items):,} Wikidata items with a {reg['name']} id")


def _parse_point(wkt):
    m = re.match(r"Point\(([-+\d.eE]+) ([-+\d.eE]+)\)", wkt)
    return (float(m.group(2)), float(m.group(1))) if m else None  # (lat, lon)


def _distance_km(lat1, lon1, lat2, lon2):
    """Great-circle distance (haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def _check(p, found, reg):
    """Return (result, distance) for one plant and the items that have its code."""
    it = found[0]
    if len(found) > 1:
        return f"rejected: {len(found)} Wikidata items share this {reg['name']} code", ""
    if len(it["code"].split()) > 1:
        return f"rejected: the Wikidata item has several {reg['name']} codes", ""
    if it["is_power_station"] != "true":
        return "rejected: the Wikidata item is not a power station", ""
    if it["countries"] and reg["country"] not in it["countries"].split():
        return f"rejected: the Wikidata item is not in {reg['country_name']}", ""
    if not it["coordinates"]:
        return "rejected: the Wikidata item has no coordinates", ""
    points = [pt for pt in map(_parse_point, it["coordinates"].split(";")) if pt]
    d = min(_distance_km(float(p["latitude"]), float(p["longitude"]), lat, lon)
            for lat, lon in points)
    if d > reg["max_km"]:
        return f"rejected: Wikidata location more than {reg['max_km']:.0f} km away", f"{d:.2f}"
    return (f"checked: exact {reg['name']} code, power station, "
            f"in {reg['country_name']}, location fits"), f"{d:.2f}"


def link_plants_wikidata(plants, refresh=False):
    """Set plant['wikidata_id'] where all checks pass; write the decisions file.

    Returns {registry name: Counter of checked/rejected} and a Counter of
    rejection reasons.
    """
    registries = {}
    for reg in PLANT_REGISTRIES:
        if refresh or not reg["cache"].exists():
            refresh_wikidata_registry(reg)
        index = defaultdict(list)
        with open(reg["cache"], encoding="utf-8", newline="") as f:
            for it in csv.DictReader(f):
                for code in it["code"].split():
                    index[code].append(it)
        registries[reg["prefix"]] = (re.compile(rf"{reg['prefix']}0*(\d+)"), reg, index)

    decisions = []
    for p in plants:
        p["wikidata_id"] = None
        entry = registries.get(p["id"][:3])
        if not entry:
            continue
        pattern, reg, index = entry
        m = pattern.fullmatch(p["id"])
        found = index.get(m.group(1), []) if m else []
        if not found:
            continue  # no Wikidata item has this code: nothing to record
        result, distance = _check(p, found, reg)
        if result.startswith("checked"):
            p["wikidata_id"] = found[0]["qid"]
        decisions.append({"gppd_idnr": p["id"], "name": p["name"], "registry": reg["name"],
                          "code": m.group(1), "wikidata_id": found[0]["qid"],
                          "wikidata_label": found[0]["label"],
                          "distance_km": distance, "result": result})

    with open(config.WIKIDATA_PLANT_LINKS_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["gppd_idnr", "name", "registry", "code",
                                          "wikidata_id", "wikidata_label",
                                          "distance_km", "result"])
        w.writeheader()
        w.writerows(decisions)
    outcome = defaultdict(Counter)
    for d in decisions:
        outcome[d["registry"]][d["result"].split(":")[0]] += 1
    return outcome, Counter(f"{d['registry']:<5} {d['result']}" for d in decisions
                            if d["result"].startswith("rejected"))


def link_organisations(plants, wikidata_top_n=0):
    """Return {label: (iri, wikidata_id or None)} for every organisation used.

    With wikidata_top_n=0 only the cache is used (no network). Only rows whose
    result starts with "checked" produce an owl:sameAs link.
    """
    labels = {config.WRI_LABEL, config.GROUP_LABEL}
    owners = Counter()
    owner_countries = defaultdict(set)
    for p in plants:
        for key in ("owner", "source", "geolocation_source", "generation_source"):
            if p[key]:
                labels.add(p[key])
        if p["owner"]:
            owners[p["owner"]] += 1
            owner_countries[p["owner"]].add(p["country_code"])

    cache = load_wikidata_cache()
    needs_check = any(r["result"] == UNCHECKED for r in cache.values())
    if wikidata_top_n or needs_check:
        cache = update_wikidata_cache(owners, owner_countries, wikidata_top_n)

    orgs = {}
    for lab, iri in organisation_iris(labels).items():
        row = cache.get(lab, {})
        qid = row.get("wikidata_id") if row.get("result", "").startswith("checked") else None
        orgs[lab] = (iri, qid or None)
    return orgs
