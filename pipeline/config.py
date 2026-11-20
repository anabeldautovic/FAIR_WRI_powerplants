"""Shared settings: file paths, namespaces and fixed values used by every stage."""

from pathlib import Path

from rdflib import Namespace, URIRef

# --- paths -------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
RAW_CSV = ROOT / "data" / "raw" / "global_power_plant_database.csv"
RAW_CSV_URL = (
    "https://wri-dataportal-prod.s3.amazonaws.com/manual/"
    "global_power_plant_database_v_1_3.zip"
)
EU_COUNTRIES_CSV = ROOT / "data" / "reference" / "eu-countries.csv"
WIKIDATA_CACHE_CSV = ROOT / "data" / "reference" / "wikidata-orgs.csv"
WIKIDATA_EIA_CSV = ROOT / "data" / "reference" / "wikidata-eia-plants.csv"
WIKIDATA_REPD_CSV = ROOT / "data" / "reference" / "wikidata-repd-plants.csv"
WIKIDATA_PLANT_LINKS_CSV = ROOT / "data" / "reference" / "wikidata-plant-links.csv"
ISSUES_CSV = ROOT / "data" / "issues.csv"
OUTPUT_TTL = ROOT / "data" / "output" / "gppd-ld.ttl"
ONTOLOGY_TTL = ROOT / "ontology" / "gppd.ttl"
SHAPES_TTL = ROOT / "shacl" / "gppd-shapes.ttl"

# --- namespaces --------------------------------------------------------
BASE = "https://w3id.org/gppd-ld/"
GPPD = Namespace(BASE + "ontology#")
PLANT = Namespace(BASE + "plant/")
ORG = Namespace(BASE + "org/")
OBS = Namespace(BASE + "obs/")
FUEL = Namespace(BASE + "fuel/")
METHOD = Namespace(BASE + "method/")
DATASET = URIRef(BASE + "dataset")
DISTRIBUTION = URIRef(BASE + "dataset/ttl")

DBO = Namespace("http://dbpedia.org/ontology/")
OEO = Namespace("http://openenergy-platform.org/ontology/oeo/")
GEO = Namespace("http://www.opengis.net/ont/geosparql#")
SF = Namespace("http://www.opengis.net/ont/sf#")
ADMS = Namespace("http://www.w3.org/ns/adms#")
QB = Namespace("http://purl.org/linked-data/cube#")
SDMX_DIM = Namespace("http://purl.org/linked-data/sdmx/2009/dimension#")
SDMX_MEASURE = Namespace("http://purl.org/linked-data/sdmx/2009/measure#")
SDMX_ATTR = Namespace("http://purl.org/linked-data/sdmx/2009/attribute#")
UNIT = Namespace("http://qudt.org/vocab/unit/")
COUNTRY = Namespace("http://publications.europa.eu/resource/authority/country/")
WD = Namespace("http://www.wikidata.org/entity/")

PREFIXES = {
    "dbo": DBO, "oeo": OEO, "geo": GEO, "sf": SF, "adms": ADMS, "qb": QB,
    "sdmx-dimension": SDMX_DIM, "sdmx-measure": SDMX_MEASURE,
    "sdmx-attribute": SDMX_ATTR, "unit": UNIT, "country": COUNTRY, "wd": WD,
    "gppd": GPPD, "plant": PLANT, "org": ORG, "obs": OBS, "fuel": FUEL,
    "method": METHOD,
}

# --- controlled values -------------------------------------------------
# The 15 GPPD fuel categories (skos:notation) -> concept IRI.
FUELS = [
    "Biomass", "Coal", "Cogeneration", "Gas", "Geothermal", "Hydro", "Nuclear",
    "Oil", "Other", "Petcoke", "Solar", "Storage", "Waste", "Wave and Tidal", "Wind",
]
FUEL_IRI = {f: FUEL[f.title().replace(" ", "")] for f in FUELS}

# The 5 estimation methods. NO-ESTIMATION is deliberately not here.
METHODS = {
    "CAPACITY-FACTOR-V1": "Capacity factor model v1",
    "HYDRO-V1": "Hydro model v1",
    "SOLAR-V1": "Solar model v1",
    "SOLAR-V1-NO-AGE": "Solar model v1 without age",
    "WIND-V1": "Wind model v1",
}
METHOD_IRI = {m: METHOD[m] for m in METHODS}

REPORTED_YEARS = range(2013, 2020)   # generation_gwh_2013 .. 2019
ESTIMATED_YEARS = range(2013, 2018)  # estimated_generation_gwh_2013 .. 2017

# GPPD codes that are not ISO alpha-3 but have a known EU authority code.
COUNTRY_ALIASES = {"KOS": "XKX"}  # Kosovo: GPPD uses KOS, EU table uses XKX

# --- organisations with fixed IRIs ------------------------------------
WRI_LABEL = "World Resources Institute"
WRI = ORG["wri"]
GROUP_LABEL = "Group 2, Data Interoperability"
GROUP = ORG["group2"]
WEPP_AGENCY = "S&P Global Platts WEPP"

# --- dataset metadata --------------------------------------------------
DATASET_TITLE = "Global Power Plant Database as Linked Data"
DATASET_DESCRIPTION = (
    "5-star Linked Data version of the WRI Global Power Plant Database v1.3.0: "
    "about 35,000 power plants with capacity, fuel, location, owner and annual "
    "reported and estimated electricity generation."
)
DATASET_VERSION = "1.0.0"
SOURCE_PAGE = URIRef("https://datasets.wri.org/dataset/globalpowerplantdatabase")
LICENSE = URIRef("https://creativecommons.org/licenses/by/4.0/")
DOWNLOAD_URL = URIRef(
    "https://github.com/anabeldautovic/FAIR_WRI_powerplants/releases/download/v1.0/gppd-ld.ttl"
)
MEDIA_TYPE = URIRef("https://www.iana.org/assignments/media-types/text/turtle")

# Wikidata API etiquette: identify the tool, no personal details.
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
USER_AGENT = "gppd-ld-pipeline/1.0 (university linked-data project)"
