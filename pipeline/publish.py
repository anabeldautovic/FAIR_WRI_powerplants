"""Stage 6 - Publish: write the Turtle file and, optionally, upload to Fuseki.

Fuseki settings come from environment variables or a local .env file
(never from code; .env is in .gitignore):
    FUSEKI_URL       e.g. https://example.org/fuseki/G02
    FUSEKI_USER      user name
    FUSEKI_PASSWORD  password
The upload replaces the default graph with the data (PUT) and then adds the
ontology (POST), using the SPARQL Graph Store Protocol endpoint /data.
"""

import gzip
import os
import shutil

import requests

from . import config


def write_turtle(graph, path=config.OUTPUT_TTL):
    path.parent.mkdir(parents=True, exist_ok=True)
    graph.serialize(destination=path, format="turtle", encoding="utf-8")
    size_mb = path.stat().st_size / 1_000_000
    print(f"  wrote {path.relative_to(config.ROOT)} ({len(graph):,} triples, {size_mb:.1f} MB)")

    # Compressed copy: small enough to keep in git, so every release snapshot
    # (and its Zenodo archive) contains the data itself.
    gz = path.with_name(path.name + ".gz")
    with open(path, "rb") as src, gzip.open(gz, "wb", compresslevel=9) as dst:
        shutil.copyfileobj(src, dst)
    print(f"  wrote {gz.relative_to(config.ROOT)} ({gz.stat().st_size / 1_000_000:.1f} MB)")


def _load_dotenv(path=config.ROOT / ".env"):
    """Read KEY=value lines from a local .env file (kept out of git).

    Variables already set in the environment win over the file.
    """
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def upload_to_fuseki(data_path=config.OUTPUT_TTL, ontology_path=config.ONTOLOGY_TTL):
    _load_dotenv()
    url = os.environ.get("FUSEKI_URL")
    user = os.environ.get("FUSEKI_USER")
    password = os.environ.get("FUSEKI_PASSWORD")
    if not url:
        raise SystemExit("Set FUSEKI_URL (and FUSEKI_USER / FUSEKI_PASSWORD) to upload.")
    endpoint = url.rstrip("/") + "/data"
    auth = (user, password) if user else None
    headers = {"Content-Type": "text/turtle; charset=utf-8"}

    for method, path in (("PUT", data_path), ("POST", ontology_path)):
        with open(path, "rb") as f:
            resp = requests.request(method, endpoint, params={"default": ""}, data=f,
                                    headers=headers, auth=auth, timeout=600)
        if not resp.ok:
            raise SystemExit(f"Fuseki {method} {path.name} failed: {resp.status_code} {resp.text[:300]}")
        print(f"  {method} {path.name} -> {resp.status_code}")
