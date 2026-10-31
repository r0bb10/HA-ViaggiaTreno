"""Normalize and join board records without merging distinct daily services."""

from collections import defaultdict
from datetime import UTC, datetime
from math import isfinite
from typing import Any

from .const import STATIC_URL

# Operator IDs are ViaggiaTreno/RFI customer IDs, not station identifiers.
OPERATORS = {
    "1": ("Trenitalia", "trenitalia"),
    "2": ("Trenitalia", "trenitalia"),
    "4": ("Trenitalia", "intercity"),
    "18": ("Trenitalia Tper", "trenitalia-tper"),
    "63": ("Trenord", "trenord"),
    "64": ("TILO", "tilo"),
    "910": ("Ferrovie del Sud Est", "ferrovie-sud-est"),
}
CATEGORIES = {"REG", "RV", "RE", "S", "IC", "ICN", "EC", "EN", "FR", "FA", "FB"}


def service_key(train: dict) -> str | None:
    """Missing identity fields must never cause a speculative match."""
    number = train.get("numeroTreno")
    origin = train.get("codOrigine")
    date = train.get("dataPartenzaTrenoAsDate")
    if not date:
        date = train.get("dataPartenzaTreno") or train.get("millisDataPartenza")
    if number is None or not origin or date is None or date == "":
        return None
    return f"{date}:{origin}:{number}"


def _timestamp(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        if not isfinite(value):
            return None
        return datetime.fromtimestamp(value / 1000, UTC).isoformat()
    except ValueError, OverflowError, OSError:
        return None


def _platform(train: dict, side: str) -> tuple[str | None, str | None]:
    for kind, label in (("Effettivo", "actual"), ("Programmato", "planned")):
        value = train.get(f"binario{kind}{side}Descrizione")
        if value is not None and str(value).strip():
            return str(value).strip(), label
    return None, None


def normalize(train: dict, direction: str, counterpart: dict | None) -> dict:
    """Produce a stable, card-independent train contract."""
    arrival = train if direction == "arrivi" else counterpart or {}
    departure = train if direction == "partenze" else counterpart or {}
    side = "Arrivo" if direction == "arrivi" else "Partenza"
    platform, platform_source = _platform(train, side)
    arrival_platform, arrival_platform_source = _platform(arrival, "Arrivo")
    departure_platform, departure_platform_source = _platform(departure, "Partenza")
    operator_code = str(train.get("codiceCliente", ""))
    operator_name, operator_asset = OPERATORS.get(
        operator_code,
        (f"Operator {operator_code}" if operator_code else None, "unknown"),
    )
    category = train.get("categoriaDescrizione") or train.get("categoria")
    category_code = str(train.get("categoria") or category or "").upper()
    category_asset = category_code.lower() if category_code in CATEGORIES else "unknown"
    delay = train.get("ritardo")
    if (
        isinstance(delay, bool)
        or not isinstance(delay, (int, float))
        or not isfinite(delay)
    ):
        delay = None
    return {
        "service_id": service_key(train),
        "train_number": str(train["numeroTreno"]),
        "service_date": train.get("dataPartenzaTrenoAsDate"),
        "service_timestamp": train.get("dataPartenzaTreno")
        or train.get("millisDataPartenza"),
        "origin_station_id": train.get("codOrigine"),
        "origin": arrival.get("origine") or train.get("origine"),
        "destination": departure.get("destinazione") or train.get("destinazione"),
        "scheduled": _timestamp(train.get(f"orario{side}")),
        "scheduled_arrival": _timestamp(arrival.get("orarioArrivo")),
        "scheduled_departure": _timestamp(departure.get("orarioPartenza")),
        "delay": delay,
        "platform": platform,
        "platform_source": platform_source,
        "arrival_platform": arrival_platform,
        "arrival_platform_source": arrival_platform_source,
        "departure_platform": departure_platform,
        "departure_platform_source": departure_platform_source,
        "operator_code": operator_code or None,
        "operator": operator_name,
        "operator_icon": f"{STATIC_URL}/operators/{operator_asset}.svg",
        "category_code": category_code or None,
        "category": category,
        "category_icon": f"{STATIC_URL}/categories/{category_asset}.svg",
        "cancelled": train.get("provvedimento") == 1,
        "arrived": train.get("arrivato") is True,
        "in_station": train.get("inStazione") is True,
        "not_started": train.get("nonPartito") is True,
        "last_detection": _timestamp(train.get("ultimoRilev")),
        "counterpart_matched": counterpart is not None,
    }


def merge_boards(arrivals: list[dict], departures: list[dict]) -> dict[str, list[dict]]:
    """Enrich both lists, matching only unique complete service identities."""
    indexes = {}
    for direction, rows in (("arrivi", arrivals), ("partenze", departures)):
        index: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            if key := service_key(row):
                index[key].append(row)
        indexes[direction] = index
    result = {}
    for direction, rows, opposite in (
        ("arrivi", arrivals, "partenze"),
        ("partenze", departures, "arrivi"),
    ):
        normalized = []
        for row in rows:
            key = service_key(row)
            matches = indexes[opposite].get(key, [])
            counterpart = (
                matches[0]
                if len(matches) == 1 and len(indexes[direction].get(key, [])) == 1
                else None
            )
            normalized.append(normalize(row, direction, counterpart))
        result[direction] = sorted(
            normalized,
            key=lambda row: (row["scheduled"] or "9999", row["train_number"]),
        )
    return result
