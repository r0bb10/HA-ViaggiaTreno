from copy import deepcopy
from datetime import UTC, datetime

import pytest

from custom_components.viaggiatreno.api import request_date
from custom_components.viaggiatreno.models import merge_boards, normalize


def test_join_and_platforms(boards):
    data = merge_boards(*boards)
    arrival = data["arrivi"][0]
    departure = data["partenze"][0]
    assert arrival["origin"] == "MILANO CENTRALE"
    assert arrival["destination"] == "LA SPEZIA CENTRALE"
    assert arrival["platform"] == "2"
    assert arrival["platform_source"] == "planned"
    assert arrival["departure_platform"] == "3"
    assert departure["platform"] == "3"
    assert departure["platform_source"] == "actual"
    assert arrival["operator"] == "Trenitalia"
    assert arrival["category"] == "IC"
    assert arrival["scheduled"] == "2026-10-29T12:01:00+00:00"
    assert arrival["counterpart_matched"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("dataPartenzaTrenoAsDate", "2026-10-30"),
        ("codOrigine", "S99999"),
        ("codOrigine", None),
        ("dataPartenzaTrenoAsDate", None),
    ],
)
def test_no_unsafe_join(boards, field, value):
    arrivals, departures = deepcopy(boards)
    departures[0][field] = value
    data = merge_boards(arrivals, departures)
    assert data["arrivi"][0]["destination"] is None
    assert not data["arrivi"][0]["counterpart_matched"]


def test_duplicates_and_one_sided_services(boards):
    arrivals, departures = boards
    assert (
        merge_boards(arrivals, [*departures, *departures])["arrivi"][0]["destination"]
        is None
    )
    assert len(merge_boards([], departures)["partenze"]) == 1
    assert merge_boards(arrivals, [])["arrivi"][0]["origin"] == "MILANO CENTRALE"
    assert merge_boards([], []) == {"arrivi": [], "partenze": []}


@pytest.mark.parametrize("code", [18, "18"])
def test_trenitalia_tper_logo(code):
    row = normalize({"numeroTreno": 123, "codiceCliente": code}, "arrivi", None)
    assert row["operator"] == "Trenitalia Tper"
    assert row["operator_icon"] == (
        "/viaggiatreno/static/operators/trenitalia-tper.svg"
    )


def test_unknown_and_invalid_values():
    row = normalize(
        {
            "numeroTreno": 123,
            "codiceCliente": 999,
            "categoria": "NEW",
            "ritardo": None,
            "orarioArrivo": float("inf"),
        },
        "arrivi",
        None,
    )
    assert row["operator"] == "Operator 999"
    assert row["operator_icon"].endswith("unknown.svg")
    assert row["category_icon"].endswith("unknown.svg")
    assert row["scheduled"] is None
    assert row["delay"] is None
    assert row["platform"] is None


@pytest.mark.parametrize(
    "code,name,asset",
    [(64, "TILO", "tilo"), (910, "Ferrovie del Sud Est", "ferrovie-sud-est")],
)
def test_additional_operator_logos(code, name, asset):
    row = normalize({"numeroTreno": 123, "codiceCliente": code}, "arrivi", None)
    assert row["operator"] == name
    assert row["operator_icon"] == f"/viaggiatreno/static/operators/{asset}.svg"


@pytest.mark.parametrize("month,hour,offset", [(1, 13, "+0100"), (7, 14, "+0200")])
def test_rome_date_dst(month, hour, offset):
    result = request_date(datetime(2026, month, 1, 12, 0, tzinfo=UTC))
    assert f"{hour}:00:00 GMT{offset}" in result
