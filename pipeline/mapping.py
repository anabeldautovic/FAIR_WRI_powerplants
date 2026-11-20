"""Stage 4 - Map to RDF, following the application profile in docs/EXE3-GPPD_LDAP.png.

IRI patterns
    plant           https://w3id.org/gppd-ld/plant/{gppd_idnr}
    its location    https://w3id.org/gppd-ld/plant/{gppd_idnr}-geom
    WEPP identifier https://w3id.org/gppd-ld/plant/{gppd_idnr}-wepp-{wepp_id}
    observation     https://w3id.org/gppd-ld/obs/{gppd_idnr}-{reported|estimated}-{year}
    organisation    https://w3id.org/gppd-ld/org/{slug}
"""

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import DCAT, DCTERMS, OWL, PROV, RDF, RDFS, SKOS, XSD

from . import config as c


def new_graph():
    g = Graph()
    # replace=True: rdflib reserves some prefixes (e.g. "org" for the W3C
    # Organization ontology); ours must win so "org:" means our namespace.
    for prefix, ns in c.PREFIXES.items():
        g.bind(prefix, ns, override=True, replace=True)
    g.bind("dcat", DCAT)
    g.bind("dcterms", DCTERMS)
    g.bind("prov", PROV)
    g.bind("skos", SKOS)
    return g


def add_dataset_metadata(g):
    """The main dcat:Dataset, its distribution and the two generation qb:DataSets."""
    ds = c.DATASET
    g.add((ds, RDF.type, DCAT.Dataset))
    g.add((ds, DCTERMS.title, Literal(c.DATASET_TITLE, lang="en")))
    g.add((ds, DCTERMS.description, Literal(c.DATASET_DESCRIPTION, lang="en")))
    g.add((ds, DCTERMS.license, c.LICENSE))
    g.add((ds, DCTERMS.publisher, c.GROUP))
    g.add((ds, DCTERMS.source, c.SOURCE_PAGE))
    # DCAT 3 term; rdflib's built-in DCAT namespace does not list it yet.
    g.add((ds, URIRef(str(DCAT) + "version"), Literal(c.DATASET_VERSION)))
    g.add((ds, DCAT.distribution, c.DISTRIBUTION))

    g.add((c.DISTRIBUTION, RDF.type, DCAT.Distribution))
    g.add((c.DISTRIBUTION, DCAT.downloadURL, c.DOWNLOAD_URL))
    g.add((c.DISTRIBUTION, DCAT.mediaType, c.MEDIA_TYPE))
    g.add((c.DISTRIBUTION, DCTERMS.license, c.LICENSE))

    for qbds in (c.GPPD.reportedGeneration, c.GPPD.estimatedGeneration):
        g.add((qbds, RDF.type, c.QB.DataSet))
        g.add((qbds, RDF.type, DCAT.Dataset))
        g.add((qbds, c.QB.structure, c.GPPD.generationDSD))
        g.add((qbds, DCTERMS.isPartOf, ds))
    g.add((c.GPPD.reportedGeneration, RDFS.label,
           Literal("Reported annual generation 2013-2019", lang="en")))
    g.add((c.GPPD.estimatedGeneration, RDFS.label,
           Literal("Estimated annual generation 2013-2017", lang="en")))


def add_organisations(g, orgs):
    for label, (iri, qid) in orgs.items():
        g.add((iri, RDF.type, PROV.Organization))
        g.add((iri, RDFS.label, Literal(label)))
        if qid:
            g.add((iri, OWL.sameAs, c.WD[qid]))


def add_plant(g, p, orgs):
    pid = p["id"]
    s = c.PLANT[pid]
    org = lambda label: orgs[label][0]

    for t in (c.DBO.PowerStation, c.GEO.Feature, c.OEO.OEO_00000031):
        g.add((s, RDF.type, t))
    g.add((s, DCTERMS.identifier, Literal(pid)))
    g.add((s, DCTERMS.title, Literal(p["name"])))
    g.add((s, DCTERMS.isPartOf, c.DATASET))
    # capacity in MW -> watts, as xsd:double
    g.add((s, c.DBO.installedCapacity,
           Literal(float(p["capacity_mw"] * 1_000_000), datatype=XSD.double)))
    g.add((s, c.DBO.primaryFuelType, c.FUEL_IRI[p["primary_fuel"]]))
    for f in p["other_fuels"]:
        g.add((s, c.DBO.otherFuelType, c.FUEL_IRI[f]))
    if p["capacity_year"] is not None:
        g.add((s, c.GPPD.capacityDataYear, Literal(str(p["capacity_year"]), datatype=XSD.gYear)))
    if p["commissioning_year"] is not None:
        g.add((s, c.GPPD.commissioningYear, Literal(p["commissioning_year"], datatype=XSD.decimal)))
    g.add((s, c.DBO.country, p["country_iri"]))
    if p["owner"]:
        g.add((s, c.DBO.owner, org(p["owner"])))
    if p["source"]:
        g.add((s, PROV.wasAttributedTo, org(p["source"])))
    if p["url"]:
        g.add((s, PROV.hadPrimarySource, URIRef(p["url"])))
    if p.get("wikidata_id"):
        # checked link through a national registry code (see link.link_plants_wikidata)
        g.add((s, OWL.sameAs, c.WD[p["wikidata_id"]]))

    # location
    geom = c.PLANT[f"{pid}-geom"]
    g.add((s, c.GEO.hasGeometry, geom))
    g.add((geom, RDF.type, c.SF.Point))
    g.add((geom, RDF.type, c.GEO.Geometry))
    g.add((geom, c.GEO.asWKT,
           Literal(f"POINT({p['longitude']} {p['latitude']})", datatype=c.GEO.wktLiteral)))
    if p["geolocation_source"]:
        g.add((geom, PROV.wasAttributedTo, org(p["geolocation_source"])))

    # WEPP identifiers
    for w in p["wepp_ids"]:
        ident = c.PLANT[f"{pid}-wepp-{w}"]
        g.add((s, c.ADMS.identifier, ident))
        g.add((ident, RDF.type, c.GPPD.WEPPIdentifier))
        g.add((ident, RDF.type, c.ADMS.Identifier))
        g.add((ident, SKOS.notation, Literal(w)))
        g.add((ident, c.ADMS.schemaAgency, Literal(c.WEPP_AGENCY)))

    # generation observations
    for year, value in p["reported"].items():
        o = _observation(g, pid, s, "reported", year, value)
        g.add((o, c.QB.dataSet, c.GPPD.reportedGeneration))
        g.add((o, PROV.wasAttributedTo, org(p["generation_source"])))
    for year, (value, method) in p["estimated"].items():
        o = _observation(g, pid, s, "estimated", year, value)
        g.add((o, c.QB.dataSet, c.GPPD.estimatedGeneration))
        g.add((o, c.GPPD.estimationMethod, c.METHOD_IRI[method]))
        g.add((o, PROV.wasAttributedTo, c.WRI))  # WRI made the estimates


def _observation(g, pid, plant, kind, year, value):
    o = c.OBS[f"{pid}-{kind}-{year}"]
    g.add((o, RDF.type, c.QB.Observation))
    g.add((o, c.GPPD.plant, plant))
    g.add((o, c.SDMX_DIM.refPeriod, Literal(str(year), datatype=XSD.gYear)))
    g.add((o, c.SDMX_MEASURE.obsValue, Literal(value, datatype=XSD.decimal)))
    g.add((o, c.SDMX_ATTR.unitMeasure, c.UNIT["GigaW-HR"]))
    return o


def build_graph(plants, orgs):
    g = new_graph()
    add_dataset_metadata(g)
    add_organisations(g, orgs)
    for p in plants:
        add_plant(g, p, orgs)
    return g
