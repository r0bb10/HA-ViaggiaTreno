import asyncio
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import aiohttp
import pytest
from aiohttp import web

from custom_components.viaggiatreno.api import (
    NoData,
    RateLimited,
    ViaggiaTrenoClient,
    ViaggiaTrenoError,
)

TRAIN = {
    "origin_station_id": "S01700",
    "train_number": "2375",
    "service_timestamp": 1793228400000,
}
REPORT = {
    "stazioneUltimoRilevamento": "PONTECURONE",
    "oraUltimoRilevamento": 1793294820000,
}

pytestmark = pytest.mark.usefixtures("socket_enabled")


async def client_for(aiohttp_client, monkeypatch, handler):
    app = web.Application()
    app.router.add_get("/{path:.*}", handler)
    server = await aiohttp_client(app)
    monkeypatch.setattr(
        "custom_components.viaggiatreno.api.BASE_URL", str(server.make_url(""))
    )
    return server


async def test_api_network_roundtrip(aiohttp_client, monkeypatch, boards):
    paths = []

    async def handler(request):
        paths.append(request.path)
        if "autocompleta" in request.path:
            return web.Response(text="TORTONA|S01810\nTORTONA|S01810\nVOGHERA|S01807")
        return web.json_response(boards[0] if "/arrivi/" in request.path else boards[1])

    await client_for(aiohttp_client, monkeypatch, handler)
    async with aiohttp.ClientSession() as session:
        client = ViaggiaTrenoClient(session)
        stations = await client.search_stations("Tortona")
        assert len(stations) == 2
        data = await client.boards("S01810", datetime.now(UTC))
        assert data == boards
        assert any("GMT+" in path for path in paths)


@pytest.mark.parametrize("body", ["<html>Error</html>", "null", "{}", '[{"foo":1}]'])
async def test_reject_invalid_board(aiohttp_client, monkeypatch, body):
    async def handler(request):
        return web.Response(text=body)

    await client_for(aiohttp_client, monkeypatch, handler)
    async with aiohttp.ClientSession() as session:
        with pytest.raises(ViaggiaTrenoError):
            await ViaggiaTrenoClient(session).board(
                "S01810", "arrivi", datetime.now(UTC)
            )


async def test_rate_limit(aiohttp_client, monkeypatch):
    async def handler(request):
        return web.Response(status=429, headers={"Retry-After": "123"})

    await client_for(aiohttp_client, monkeypatch, handler)
    async with aiohttp.ClientSession() as session:
        with pytest.raises(RateLimited) as exc:
            await ViaggiaTrenoClient(session).search_stations("Tortona")
        assert exc.value.retry_after == 123


async def test_streaming_json(aiohttp_client, monkeypatch):
    async def handler(request):
        response = web.StreamResponse(headers={"Content-Type": "application/json"})
        await response.prepare(request)
        for chunk in (b'[{"numero', b'Treno":1', b"}]"):
            await response.write(chunk)
        await response.write_eof()
        return response

    await client_for(aiohttp_client, monkeypatch, handler)
    async with aiohttp.ClientSession() as session:
        assert await ViaggiaTrenoClient(session).board(
            "S01810", "arrivi", datetime.now(UTC)
        ) == [{"numeroTreno": 1}]


async def test_last_report(aiohttp_client, monkeypatch):
    async def handler(request):
        assert request.path == "/andamentoTreno/S01700/2375/1793228400000"
        return web.json_response(
            {
                "stazioneUltimoRilevamento": "PONTECURONE",
                "oraUltimoRilevamento": 1793294820000,
            }
        )

    await client_for(aiohttp_client, monkeypatch, handler)
    async with aiohttp.ClientSession() as session:
        client = ViaggiaTrenoClient(session)
        result = await client.last_report(
            {
                "origin_station_id": "S01700",
                "train_number": "2375",
                "service_timestamp": 1793228400000,
            }
        )
        assert result == {
            "station": "PONTECURONE",
            "timestamp": "2026-10-29T17:27:00+00:00",
        }
        with pytest.raises(ViaggiaTrenoError):
            await client.last_report({"origin_station_id": "../../outside"})


async def test_request_connection_timeout():
    from unittest.mock import MagicMock

    session = MagicMock()
    session.get.return_value.__aenter__ = AsyncMock(side_effect=TimeoutError)
    client = ViaggiaTrenoClient(session)
    with pytest.raises(ViaggiaTrenoError):
        await client._get("example")
    timeout = session.get.call_args.kwargs["timeout"]
    assert timeout.connect == 5
    assert timeout.total == 20


async def test_no_content_is_not_a_successful_board(aiohttp_client, monkeypatch):
    async def handler(request):
        return web.Response(status=204)

    await client_for(aiohttp_client, monkeypatch, handler)
    async with aiohttp.ClientSession() as session:
        client = ViaggiaTrenoClient(session)
        assert await client.last_report(TRAIN) == {"station": None, "timestamp": None}
        with pytest.raises(NoData):
            await client.board("S01810", "arrivi", datetime.now(UTC))


@pytest.mark.parametrize(
    "data",
    [
        None,
        {},
        {**REPORT, "stazioneUltimoRilevamento": "--"},
        {**REPORT, "oraUltimoRilevamento": 0},
        {**REPORT, "oraUltimoRilevamento": None},
    ],
)
async def test_missing_report_is_not_a_connection_failure(data):
    client = ViaggiaTrenoClient(None)
    client._get = AsyncMock(return_value=json.dumps(data))
    assert await client.last_report(TRAIN) == {"station": None, "timestamp": None}


async def test_report_requests_share_inflight_task_and_cache(monkeypatch):
    import json

    started = asyncio.Event()
    finish = asyncio.Event()
    clock = [100.0]
    monkeypatch.setattr(
        "custom_components.viaggiatreno.api.monotonic", lambda: clock[0]
    )
    client = ViaggiaTrenoClient(None)

    async def fetch(path):
        started.set()
        await finish.wait()
        return json.dumps(REPORT)

    client._get = AsyncMock(side_effect=fetch)
    first = asyncio.create_task(client.last_report(TRAIN))
    await started.wait()
    second = asyncio.create_task(client.last_report(TRAIN))
    finish.set()
    results = await asyncio.gather(first, second)
    assert results[0] == results[1]
    assert client._get.await_count == 1
    results[0]["station"] = "changed by caller"
    assert (await client.last_report(TRAIN))["station"] == "PONTECURONE"
    assert client._get.await_count == 1
    clock[0] += 16
    await client.last_report(TRAIN)
    assert client._get.await_count == 2


async def test_cancelling_a_caller_does_not_cancel_shared_report():
    import json

    client = ViaggiaTrenoClient(None)
    started = asyncio.Event()
    finish = asyncio.Event()

    async def fetch(path):
        started.set()
        await finish.wait()
        return json.dumps(REPORT)

    client._get = AsyncMock(side_effect=fetch)
    first = asyncio.create_task(client.last_report(TRAIN))
    await started.wait()
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    second = asyncio.create_task(client.last_report(TRAIN))
    finish.set()
    assert (await second)["station"] == "PONTECURONE"
    assert client._get.await_count == 1


async def test_report_cache_keeps_service_dates_and_origins_separate():
    import json

    client = ViaggiaTrenoClient(None)
    client._get = AsyncMock(return_value=json.dumps(REPORT))
    for train in [
        TRAIN,
        {**TRAIN, "origin_station_id": "S04702"},
        {**TRAIN, "service_timestamp": TRAIN["service_timestamp"] + 86400000},
    ]:
        await client.last_report(train)
    assert client._get.await_count == 3


async def test_report_errors_are_not_cached():
    import json

    client = ViaggiaTrenoClient(None)
    client._get = AsyncMock(
        side_effect=[ViaggiaTrenoError("Offline"), json.dumps(REPORT)]
    )
    with pytest.raises(ViaggiaTrenoError):
        await client.last_report(TRAIN)
    assert (await client.last_report(TRAIN))["station"] == "PONTECURONE"
    assert client._get.await_count == 2


async def test_report_cache_is_bounded(monkeypatch):
    import json

    monkeypatch.setattr("custom_components.viaggiatreno.api.MAX_REPORTS", 2)
    client = ViaggiaTrenoClient(None)
    client._get = AsyncMock(return_value=json.dumps(REPORT))
    for number in ("1", "2", "3"):
        await client.last_report({**TRAIN, "train_number": number})
    assert len(client._report_cache) == 2


async def test_client_shutdown_cancels_pending_reports():
    client = ViaggiaTrenoClient(None)
    started = asyncio.Event()

    async def fetch(path):
        started.set()
        await asyncio.Event().wait()

    client._get = AsyncMock(side_effect=fetch)
    request = asyncio.create_task(client.last_report(TRAIN))
    await started.wait()
    await client.async_close()
    with pytest.raises(asyncio.CancelledError):
        await request
    assert not client._report_tasks
    assert not client._report_cache
    with pytest.raises(ViaggiaTrenoError):
        await client.last_report(TRAIN)
