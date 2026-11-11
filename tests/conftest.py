"""Offline integration tests; live checks remain private under .dev/."""

from copy import deepcopy
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.viaggiatreno.api import Station


@pytest.fixture(autouse=True)
def enable_custom(enable_custom_integrations):
    pass


@pytest.fixture(autouse=True)
def writable_config_dir(hass, tmp_path):
    """Keep integration-installed frontend files inside each test's temp config."""
    hass.config.config_dir = str(tmp_path)


@pytest.fixture
def boards():
    common = {
        "numeroTreno": 665,
        "codOrigine": "S01700",
        "dataPartenzaTrenoAsDate": "2026-10-29",
        "codiceCliente": 4,
        "categoria": "IC",
        "categoriaDescrizione": "IC",
        "ritardo": 22,
    }
    return (
        [
            {
                **common,
                "origine": "MILANO CENTRALE",
                "orarioArrivo": 1793275260000,
                "binarioProgrammatoArrivoDescrizione": "2",
            }
        ],
        [
            {
                **common,
                "destinazione": "LA SPEZIA CENTRALE",
                "orarioPartenza": 1793275380000,
                "binarioEffettivoPartenzaDescrizione": "3",
                "binarioProgrammatoPartenzaDescrizione": "2",
            }
        ],
    )


@pytest.fixture
def mock_api(boards):
    with (
        patch(
            "custom_components.viaggiatreno.api.ViaggiaTrenoClient.search_stations",
            new_callable=AsyncMock,
            return_value=[Station("S01810", "TORTONA")],
        ) as search,
        patch(
            "custom_components.viaggiatreno.api.ViaggiaTrenoClient.boards",
            new_callable=AsyncMock,
            side_effect=lambda *args: deepcopy(boards),
        ) as fetch,
    ):
        yield search, fetch
