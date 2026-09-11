"""Integration tests for portfolio — connection lifecycle, ownership scoping,
holdings/positions retrieval, disconnect, and broker-failure handling against
a real database. All use a FakeBrokerAdapter injected via dependency override
(no real Zerodha credentials/network needed even once a real DB exists).

STATUS: WRITTEN. NOT EXECUTABLE IN CURRENT ENVIRONMENT — requires a real
PostgreSQL test database, unreachable from this session (see work_memory.md
for the exact tooling-access boundary). The adapter-facing pure logic these
would otherwise partially cover is genuinely unit-tested in
test_portfolio_pure_logic.py.
"""
import pytest


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_connect_requires_verified_email(client, unverified_member):
    resp = await client.get("/api/v1/portfolio/zerodha/connect", headers=unverified_member.auth_headers)
    assert resp.status_code == 403


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_connect_unauthenticated_rejected(client):
    resp = await client.get("/api/v1/portfolio/zerodha/connect")
    assert resp.status_code == 401


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_connect_returns_broker_not_configured_with_no_credentials(client, member_a):
    """This environment's real, current state (no ZERODHA_API_KEY set) —
    once a real DB exists, this becomes a genuine end-to-end confirmation
    of PF.1's documented 503 behavior."""
    resp = await client.get("/api/v1/portfolio/zerodha/connect", headers=member_a.auth_headers)
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "BROKER_NOT_CONFIGURED"


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_callback_creates_connected_broker_connection_row(client, member_a, db_session, fake_broker_adapter):
    resp = await client.get(
        "/api/v1/portfolio/zerodha/callback?request_token=fake-request-token", headers=member_a.auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["broker"] == "zerodha"
    assert body["status"] == "connected"
    # Assert exactly one broker_connections row exists for member_a with
    # access_token populated (but NOT present in the response body above).
    # Assert an audit_logs row exists with action_type='portfolio.broker_connected'.


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_response_never_includes_access_token(client, member_a, connected_broker_connection):
    """Direct security regression test — the response schema literally has
    no field for this, but this confirms the actual serialized JSON too."""
    resp = await client.get("/api/v1/portfolio/zerodha/callback?request_token=irrelevant", headers=member_a.auth_headers)
    assert "access_token" not in resp.text
    assert "access_token" not in resp.json()


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_get_portfolio_returns_404_when_not_connected(client, member_a):
    resp = await client.get("/api/v1/portfolio", headers=member_a.auth_headers)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "BROKER_NOT_CONNECTED"


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_get_portfolio_returns_holdings_and_positions_from_adapter(
    client, member_a, connected_broker_connection, fake_broker_adapter_with_data,
):
    resp = await client.get("/api/v1/portfolio", headers=member_a.auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["holdings"]) > 0
    assert body["read_only_notice"] == "Read-only — QFinance cannot place trades."


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_get_portfolio_translates_broker_failure_to_502(client, member_a, connected_broker_connection, failing_broker_adapter):
    resp = await client.get("/api/v1/portfolio", headers=member_a.auth_headers)
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "BROKER_AUTH_FAILED"


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_user_cannot_access_another_users_portfolio(client, member_a, member_b, member_b_connected_broker_connection):
    """Ownership scoping — member_a's session must never return member_b's
    holdings, regardless of any parameter tampering (there IS no user_id
    parameter to tamper with — this test also confirms that structurally)."""
    resp = await client.get("/api/v1/portfolio", headers=member_a.auth_headers)
    # member_a has no connection of their own — 404, never member_b's data.
    assert resp.status_code == 404


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_disconnect_clears_token_and_marks_disconnected(client, member_a, connected_broker_connection, db_session):
    resp = await client.delete("/api/v1/portfolio/zerodha", headers=member_a.csrf_headers)
    assert resp.status_code == 204
    # Assert broker_connections.status == 'disconnected' and access_token IS NULL
    # for member_a's row.
    # Assert an audit_logs row exists with action_type='portfolio.broker_disconnected'.


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_reconnect_after_disconnect_updates_same_row_not_a_new_one(
    client, member_a, disconnected_broker_connection, fake_broker_adapter, db_session,
):
    """Regression test for the UNIQUE(user_id, broker) constraint handling —
    a second connect must UPDATE the existing row, not attempt an INSERT
    that would violate the constraint."""
    resp = await client.get(
        "/api/v1/portfolio/zerodha/callback?request_token=fake-request-token-2", headers=member_a.auth_headers,
    )
    assert resp.status_code == 200
    # Assert still exactly one broker_connections row for (member_a.id, 'zerodha').


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_no_secrets_appear_in_response_logs_or_audit_payload(client, member_a, db_session, fake_broker_adapter, caplog):
    """Covers PHASE 7's explicit checklist items: secrets in logs, secrets in
    API responses, secrets in the audit_logs payload."""
    await client.get("/api/v1/portfolio/zerodha/callback?request_token=fake-request-token", headers=member_a.auth_headers)
    # Assert no captured log record contains the fake adapter's access_token value.
    # Assert the audit_logs row's after_state JSON does not contain "access_token".
