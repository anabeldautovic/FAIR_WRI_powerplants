"""Stage 5 - Validate: check the RDF (data + ontology) against shacl/gppd-shapes.ttl.

The SKOS schemes and gppd:generationDSD live in ontology/gppd.ttl, and the
shapes need them in the same graph as the data, so both are merged first.
Violations make the pipeline fail; warnings are only printed.
"""

from collections import Counter

from pyshacl import validate as shacl_validate
from rdflib import Graph
from rdflib.namespace import SH

from . import config


def validate(data_graph):
    ontology = Graph().parse(config.ONTOLOGY_TTL, format="turtle")
    shapes = Graph().parse(config.SHAPES_TTL, format="turtle")

    combined = Graph()
    for t in data_graph:
        combined.add(t)
    for t in ontology:
        combined.add(t)

    conforms, report, _ = shacl_validate(
        combined, shacl_graph=shapes, inference="none",
        advanced=True, inplace=True, allow_warnings=True,
    )

    counts = Counter()
    for result in report.subjects(SH.resultSeverity, None):
        severity = report.value(result, SH.resultSeverity).split("#")[-1]
        message = report.value(result, SH.resultMessage) or "(no message)"
        counts[(severity, str(message))] += 1

    violations = sum(n for (sev, _), n in counts.items() if sev == "Violation")
    warnings = sum(n for (sev, _), n in counts.items() if sev == "Warning")
    print(f"  SHACL: {violations} violation(s), {warnings} warning(s)")
    for (sev, msg), n in counts.most_common():
        print(f"    {n:>7}  {sev:<9} {msg}")
    return violations == 0, report
