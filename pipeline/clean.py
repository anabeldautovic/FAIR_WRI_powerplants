"""Stage 2 - Clean: deterministic fixes only.

The output is one plain dict per plant, with values already parsed into the
right Python type (Decimal, int, list, ...). Missing optional values are None.
Rules:
  * whitespace around a value is removed (and logged);
  * a value that cannot be parsed is dropped and logged, never guessed;
  * a plant missing something the profile requires ([1]) is dropped and logged.
"""

import re
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from . import config

# Characters that are not allowed in an IRI (RFC 3987) and break Turtle.
_BAD_IRI_CHARS = re.compile(r'[<>"{}|\\^`]')


# Typical traces of UTF-8 text that was decoded as Windows-1252 ("mojibake"),
# e.g. "SvanemÃ¸lle" for "Svanemølle" or "lâ€™Electricite" for "l’Electricite".
_MOJIBAKE = re.compile("â€|Ã[\u0080-¿]|Â[\u0080-¿]")


def _fix_text(row_id, col, val, log):
    """Deterministic text repairs; each change is logged."""
    if val != val.strip():
        log.add(row_id, col, val, "leading/trailing whitespace removed")
        val = val.strip()
    if _MOJIBAKE.search(val):
        try:
            # Reversing the wrong decoding is exact: it either works fully or fails.
            fixed = val.encode("cp1252").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            log.add(row_id, col, val, "looks like broken encoding but cannot be repaired; kept as given")
        else:
            log.add(row_id, col, val, "broken character encoding (mojibake) repaired")
            val = fixed
    if "\\'" in val:
        log.add(row_id, col, val, "escaped apostrophe \\' replaced by '")
        val = val.replace("\\'", "'")
    return val


def _decimal(text):
    try:
        d = Decimal(text)
    except InvalidOperation:
        return None
    return d if d.is_finite() else None


def _clean_url(row_id, url, log):
    """Return a usable IRI for the source document, or None."""
    if not url:
        return None
    if re.search(r"[\s;,]\s*(https?|ftp)://", url, re.I):
        # Two or more URLs in one cell ("... and http://...", "...; http://..."):
        # the profile allows one source document, and choosing one would be a
        # guess. A scheme inside a URL is fine (web.archive.org/web/2014/http://...).
        log.add(row_id, "url", url, "cell holds more than one URL; not used as prov:hadPrimarySource")
        return None
    if not re.match(r"^(https?|ftp)://", url, re.I):
        log.add(row_id, "url", url, "url is not http(s)/ftp; not used")
        return None
    if _BAD_IRI_CHARS.search(url) or re.search(r"\s", url):
        # Percent-encoding spaces and these characters is lossless, so it is not a guess.
        fixed = re.sub(r'\s|[<>"{}|\\^`]', lambda m: quote(m.group(0)), url)
        log.add(row_id, "url", url, "url had spaces or characters not allowed in an IRI; percent-encoded")
        return fixed
    return url


def clean(df, log):
    plants = []
    for rec in df.to_dict("records"):
        row_id = rec["gppd_idnr"].strip() or "(no id)"

        for col, val in rec.items():
            rec[col] = _fix_text(row_id, col, val, log)

        p = clean_row(row_id, rec, log)
        if p is not None:
            plants.append(p)
    return plants


def clean_row(row_id, r, log):
    def drop(col, problem):
        log.add(row_id, col, r.get(col, ""), problem + "; plant dropped")
        return None

    # --- required values [1] -------------------------------------------
    if not r["gppd_idnr"]:
        return drop("gppd_idnr", "missing identifier")
    if not r["name"]:
        return drop("name", "missing name")

    cap = _decimal(r["capacity_mw"])
    if cap is None:
        return drop("capacity_mw", "capacity is not a number")
    if cap < 0:
        return drop("capacity_mw", "negative capacity")

    lat, lon = _decimal(r["latitude"]), _decimal(r["longitude"])
    if lat is None or lon is None:
        return drop("latitude/longitude", "coordinates missing or not numbers")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return drop("latitude/longitude", "coordinates out of range")

    if r["primary_fuel"] not in config.FUEL_IRI:
        return drop("primary_fuel", "primary fuel not one of the 15 GPPD categories")

    if not r["country"]:
        return drop("country", "missing country code")

    # --- optional values -----------------------------------------------
    other_fuels = []
    for col in ("other_fuel1", "other_fuel2", "other_fuel3"):
        f = r[col]
        if not f:
            continue
        if f not in config.FUEL_IRI:
            log.add(row_id, col, f, "fuel not one of the 15 GPPD categories; not used")
        elif f == r["primary_fuel"]:
            log.add(row_id, col, f, "other fuel repeats the primary fuel; not used")
        elif f in other_fuels:
            log.add(row_id, col, f, "other fuel listed twice; kept once")
        else:
            other_fuels.append(f)

    commissioning = None
    if r["commissioning_year"]:
        commissioning = _decimal(r["commissioning_year"])
        if commissioning is None:
            log.add(row_id, "commissioning_year", r["commissioning_year"],
                    "commissioning year is not a number; not used")
        else:
            commissioning = commissioning.normalize()  # "2006.0" -> 2006
            if commissioning == commissioning.to_integral_value():
                commissioning = commissioning.quantize(Decimal(1))

    capacity_year = None
    if r["year_of_capacity_data"]:
        y = _decimal(r["year_of_capacity_data"])
        if y is None or y != y.to_integral_value():
            log.add(row_id, "year_of_capacity_data", r["year_of_capacity_data"],
                    "capacity data year is not a whole year; not used")
        else:
            capacity_year = int(y)

    wepp_ids = []
    if r["wepp_id"]:
        # Several WEPP ids are separated by "|" (sometimes with spaces).
        for part in r["wepp_id"].split("|"):
            part = part.strip()
            if not part:
                continue
            if not part.isdigit():
                log.add(row_id, "wepp_id", part, "WEPP id is not numeric; kept as given")
            if part not in wepp_ids:
                wepp_ids.append(part)

    reported = {}
    for y in config.REPORTED_YEARS:
        col = f"generation_gwh_{y}"
        if r[col]:
            v = _decimal(r[col])
            if v is None:
                log.add(row_id, col, r[col], "generation value is not a number; no observation")
            else:
                reported[y] = v
    if reported and not r["generation_data_source"]:
        log.add(row_id, "generation_data_source", "",
                "reported generation without a data source; observations dropped")
        reported = {}

    estimated = {}
    for y in config.ESTIMATED_YEARS:
        col, note_col = f"estimated_generation_gwh_{y}", f"estimated_generation_note_{y}"
        val, note = r[col], r[note_col]
        if not val:
            continue  # empty cell -> no observation (zero is a real value)
        v = _decimal(val)
        if v is None:
            log.add(row_id, col, val, "estimated value is not a number; no observation")
        elif note not in config.METHOD_IRI:
            log.add(row_id, note_col, note,
                    "estimated value without a valid estimation method; no observation")
        else:
            estimated[y] = (v, note)

    return {
        "id": r["gppd_idnr"],
        "name": r["name"],
        "country": r["country"],
        "capacity_mw": cap,
        "latitude": lat,
        "longitude": lon,
        "primary_fuel": r["primary_fuel"],
        "other_fuels": other_fuels,
        "commissioning_year": commissioning,
        "capacity_year": capacity_year,
        "owner": r["owner"] or None,
        "source": r["source"] or None,
        "url": _clean_url(row_id, r["url"], log),
        "geolocation_source": r["geolocation_source"] or None,
        "wepp_ids": wepp_ids,
        "reported": reported,
        "generation_source": r["generation_data_source"] or None,
        "estimated": estimated,
    }
