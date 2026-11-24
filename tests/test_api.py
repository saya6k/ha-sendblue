"""Tests for the Sendblue REST client."""

import aiohttp
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.sendblue.api import (
    BASE_URL,
    SendblueAuthError,
    SendblueClient,
    SendblueContactNotVerified,
    SendblueError,
    SendblueFreePlanLimit,
    SendblueRateLimited,
)

KEY_ID = "key-id"
SECRET = "super-secret-value"


@pytest.fixture
async def client(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> SendblueClient:
    return SendblueClient(async_get_clientsession(hass), KEY_ID, SECRET)


async def test_get_lines_sends_auth_headers_and_returns_numbers(
    client: SendblueClient, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BASE_URL}/api/lines", json={"numbers": ["+15555550100"]})

    lines = await client.get_lines()

    assert lines == ["+15555550100"]
    headers = aioclient_mock.mock_calls[0][3]
    assert headers["sb-api-key-id"] == KEY_ID
    assert headers["sb-api-secret-key"] == SECRET


async def test_send_message_omits_empty_optional_fields(
    client: SendblueClient, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(
        f"{BASE_URL}/api/send-message",
        status=202,
        json={"status": "QUEUED", "message_handle": "abc"},
    )

    result = await client.send_message("+821012345678", "+15555550100", content="hi")

    assert result["message_handle"] == "abc"
    assert aioclient_mock.mock_calls[0][2] == {
        "number": "+821012345678",
        "from_number": "+15555550100",
        "content": "hi",
    }


async def test_send_message_includes_media_and_style(
    client: SendblueClient, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(
        f"{BASE_URL}/api/send-message", status=202, json={"status": "QUEUED"}
    )

    await client.send_message(
        "+821012345678",
        "+15555550100",
        content="look",
        media_url="https://example.com/a.jpg",
        send_style="celebration",
    )

    body = aioclient_mock.mock_calls[0][2]
    assert body["media_url"] == "https://example.com/a.jpg"
    assert body["send_style"] == "celebration"


@pytest.mark.parametrize("status", [401, 403])
async def test_auth_failure_raises_auth_error(
    client: SendblueClient, aioclient_mock: AiohttpClientMocker, status: int
) -> None:
    aioclient_mock.get(f"{BASE_URL}/api/lines", status=status, json={})

    with pytest.raises(SendblueAuthError):
        await client.get_lines()


async def test_unverified_contact_raises_specific_error(
    client: SendblueClient, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(
        f"{BASE_URL}/api/send-message",
        status=400,
        json={
            "status": "ERROR",
            "error_reason": "ContactHasNotBeenVerified",
            "error_message": "This contact must be verified.",
        },
    )

    with pytest.raises(SendblueContactNotVerified):
        await client.send_message("+821012345678", "+15555550100", content="hi")


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (429, {}),
        (400, {"status": "ERROR", "error_code": 4001}),
        (400, {"status": "ERROR", "error_code": 5509}),
    ],
)
async def test_rate_limits_raise_rate_limited(
    client: SendblueClient, aioclient_mock: AiohttpClientMocker, status, body
) -> None:
    aioclient_mock.post(f"{BASE_URL}/api/send-message", status=status, json=body)

    with pytest.raises(SendblueRateLimited):
        await client.send_message("+821012345678", "+15555550100", content="hi")


@pytest.mark.parametrize("code", [4007, 4008, 4009])
async def test_free_plan_limits_raise_free_plan_limit(
    client: SendblueClient, aioclient_mock: AiohttpClientMocker, code: int
) -> None:
    aioclient_mock.post(
        f"{BASE_URL}/api/send-message",
        status=400,
        json={"status": "ERROR", "error_code": code},
    )

    with pytest.raises(SendblueFreePlanLimit):
        await client.send_message("+821012345678", "+15555550100", content="hi")


async def test_error_status_in_success_response_raises(
    client: SendblueClient, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(
        f"{BASE_URL}/api/send-message",
        status=200,
        json={"status": "ERROR", "error_message": "Message failed to send"},
    )

    with pytest.raises(SendblueError, match="Message failed to send"):
        await client.send_message("+821012345678", "+15555550100", content="hi")


async def test_connection_error_raises_sendblue_error_without_secret(
    client: SendblueClient, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BASE_URL}/api/lines", exc=aiohttp.ClientError("boom"))

    with pytest.raises(SendblueError) as err:
        await client.get_lines()

    assert SECRET not in str(err.value)


async def test_list_webhooks_returns_receive_urls(
    client: SendblueClient, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(
        f"{BASE_URL}/api/account/webhooks",
        json={
            "status": "OK",
            "webhooks": {
                "receive": [
                    {"url": "https://ha.example/api/webhook/a", "secret": "s"},
                    "https://other.example/hook",
                ]
            },
        },
    )

    urls = await client.list_webhook_urls()

    assert urls == ["https://ha.example/api/webhook/a", "https://other.example/hook"]


async def test_add_webhook_posts_url_and_secret(
    client: SendblueClient, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(f"{BASE_URL}/api/account/webhooks", json={"status": "OK"})

    await client.add_webhook("https://ha.example/api/webhook/a", "s3cret")

    assert aioclient_mock.mock_calls[0][2] == {
        "webhooks": [{"url": "https://ha.example/api/webhook/a", "secret": "s3cret"}],
        "type": "receive",
    }


async def test_delete_webhook_deletes_only_given_url(
    client: SendblueClient, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.delete(f"{BASE_URL}/api/account/webhooks", json={"status": "OK"})

    await client.delete_webhook("https://ha.example/api/webhook/a")

    assert aioclient_mock.mock_calls[0][2] == {
        "webhooks": ["https://ha.example/api/webhook/a"],
        "type": "receive",
    }


async def test_shared_contacts_maps_number_to_verified(
    client: SendblueClient, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(
        f"{BASE_URL}/accounts/shared-contacts",
        json={
            "status": "SUCCESS",
            "sharedNumber": "+15555550100",
            "contacts": [
                {"id": 1, "number": "+8201012345678", "verified": False},
                {"id": 2, "number": "+821012345678", "verified": True},
                {"id": 3, "number": "+821099998888", "verified": False},
            ],
        },
    )

    contacts = await client.get_shared_contacts()

    assert contacts == {
        "+8201012345678": False,
        "+821012345678": True,
        "+821099998888": False,
    }
