"""GPPD-LD: convert the WRI Global Power Plant Database (CSV) into 5-star Linked Data.

Stages (one module each):
    ingest -> clean -> link -> mapping -> validate -> publish
Run everything with:  python -m pipeline --limit 200
"""
