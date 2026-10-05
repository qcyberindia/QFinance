"""Portfolio MVP — real app + real database (conftest.py rolled-back
savepoints). The broker is replaced by a test double that returns data in
Kite Connect's own response shape (`tradingsymbol`, `t1_quantity`, ...), so
the real normalization, encryption, authorization and error paths run end
to end without contacting Zerodha.
"""
import logging
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text

from app.core import crypto
from app.core.config import get_settings
from app.modules.portfolio import oauth_state

from app.integrations.brokers.base import BrokerConnectionError, BrokerSessionExpiredError
from app.main import app
from app.modules.portfolio import service as portfolio_service
from tests.test_community_pillars_integration import _login, _member, _walk_keys
from tests.conftest import _make_user

KITE_HOLDINGS = [
    {"tradingsymbol": "INFY", "exchange": "NSE", "isin": "INE009A01021", "quantity": 10, "t1_quantity": 0,
     "average_price": 1400.0, "last_price": 1500.0, "close_price": 1490.0, "pnl": 1000.0,
     "day_change": 10.0, "day_change_percentage": 0.67},
    {"tradingsymbol": "TCS", "exchange": "NSE", "isin": "INE467B01029", "quantity": 2, "t1_quantity": 1,
     "average_price": 3000.0, "last_price": 3300.0, "close_price": 3280.0, "pnl": 600.0,
     "day_change": 20.0, "day_change_percentage": 0.61},
]
KITE_POSITIONS = [
    {"tradingsymbol": "NIFTY24OCTFUT", "exchange": "NFO", "product": "NRML", "quantity": 25,
     "average_price": 25000.0, "last_price": 25100.0, "pnl": 2500.0},
    {"tradingsymbol": "SBIN", "exchange": "NSE", "product": "MIS", "quantity": 0,
     "average_price": 800.0, "last_price": 805.0, "pnl": 50.0},  # closed — must be dropped
]
SECRET_TOKEN = "kite-access-token-SECRET-123"


class FakeKite:
    """Test double for the BrokerAdapter protocol — Kite-shaped responses."""
    def __init__(self, holdings=None, positions=None, error: Exception | None = None):
        self.holdings, self.positions, self.error = holdings, positions, error
        self.tokens_seen: list[str] = []

    def get_login_url(self):
        return "https://kite.zerodha.com/connect/login?api_key=test&v=3"

    def exchange_request_token(self, *, request_token):
        if request_token == "bad":
            raise BrokerConnectionError("invalid request token")
        return {"access_token": SECRET_TOKEN, "broker_user_id": "AB1234"}

    def fetch_holdings(self, *, access_token):
        self.tokens_seen.append(access_token)
        if self.error:
            raise self.error
        return KITE_HOLDINGS if self.holdings is None else self.holdings

    def fetch_positions(self, *, access_token):
        if self.error:
            raise self.error
        return KITE_POSITIONS if self.positions is None else self.positions


settings = get_settings()


@pytest.fixture(autouse=True)
def _encryption_keys(monkeypatch):
    """Fixed, distinct test keys — the tests never depend on (or reveal) a
    developer's real .env secrets."""
    monkeypatch.setattr(settings, "BROKER_TOKEN_ENCRYPTION_SECRET", "test-broker-key-0123456789")
    monkeypatch.setattr(settings, "AI_KEY_ENCRYPTION_SECRET", "test-ai-key-0123456789")


@pytest.fixture
def fake_kite(monkeypatch):
    fake = FakeKite()
    monkeypatch.setattr(portfolio_service, "_DEFAULT_ADAPTER", fake)
    return fake


def _csrf(client) -> dict:
    return {"X-CSRF-Token": client.cookies.get(settings.CSRF_COOKIE_NAME)}


async def _start(client) -> str:
    """GET /zerodha/connect and return the OAuth state Kite will send back
    (carried in the login URL's redirect_params)."""
    resp = await client.get("/api/v1/portfolio/zerodha/connect")
    assert resp.status_code == 200, resp.text
    redirect_params = parse_qs(urlparse(resp.json()["login_url"]).query)["redirect_params"][0]
    return parse_qs(redirect_params)["state"][0]


async def _callback(client, *, state: str | None, request_token: str = "abc123"):
    body = {"request_token": request_token}
    if state is not None:
        body["state"] = state
    return await client.post("/api/v1/portfolio/zerodha/callback", json=body, headers=_csrf(client))


async def _connect(client, fake_kite) -> dict:
    resp = await _callback(client, state=await _start(client))
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Pure calculations
# ---------------------------------------------------------------------------

def test_normalize_holding_maps_kite_fields_and_includes_t1_quantity():
    h = portfolio_service.normalize_holding(KITE_HOLDINGS[1])
    assert h["trading_symbol"] == "TCS" and h["quantity"] == 3 and h["t1_quantity"] == 1
    assert h["invested_value"] == 9000.0 and h["current_value"] == 9900.0 and h["pnl"] == 900.0
    assert h["pnl_percent"] == 10.0 and h["day_change_value"] == 60.0


def test_summary_totals_allocation_and_concentration():
    holdings = [portfolio_service.normalize_holding(r) for r in KITE_HOLDINGS]
    s = portfolio_service.build_summary(holdings)
    assert s["invested_value"] == 23000.0  # 14000 + 9000
    assert s["current_value"] == 24900.0   # 15000 + 9900
    assert s["pnl"] == 1900.0 and s["pnl_percent"] == round(1900 / 23000 * 100, 2)
    assert s["day_change_value"] == 160.0  # 10*10 + 20*3
    assert s["top_holding_percent"] == round(15000 / 24900 * 100, 2)
    assert round(sum(h["allocation_percent"] for h in holdings), 1) == 100.0


def test_missing_prices_yield_not_available_not_estimates():
    raw = [dict(KITE_HOLDINGS[0]), dict(KITE_HOLDINGS[1], last_price=None, day_change=None)]
    holdings = [portfolio_service.normalize_holding(r) for r in raw]
    s = portfolio_service.build_summary(holdings)
    assert holdings[1]["current_value"] is None and holdings[1]["pnl"] is None
    assert s["current_value"] is None and s["pnl"] is None and s["day_change_value"] is None
    assert s["top_holding_percent"] is None and holdings[0]["allocation_percent"] is None
    assert s["invested_value"] == 23000.0  # still fully known


def test_empty_portfolio_summary():
    assert portfolio_service.build_summary([]) == {
        "holdings_count": 0, "invested_value": None, "current_value": None, "pnl": None, "pnl_percent": None,
        "day_change_value": None, "day_change_percent": None, "top_holding_percent": None, "top_five_percent": None,
    }


def test_malformed_rows_are_dropped():
    assert portfolio_service.normalize_holding({"quantity": 5}) is None
    assert portfolio_service.normalize_holding({"tradingsymbol": "X", "quantity": 0}) is None
    assert portfolio_service.normalize_holding("nope") is None


# ---------------------------------------------------------------------------
# Connection lifecycle, authorization, privacy
# ---------------------------------------------------------------------------

async def test_unauthenticated_requests_are_rejected(client):
    for path in ("/api/v1/portfolio", "/api/v1/portfolio/connection", "/api/v1/portfolio/zerodha/connect"):
        assert (await client.get(path)).status_code == 401


async def test_unverified_user_is_rejected(client, db_session):
    user = await _make_user(db_session)
    await _login(client, user)
    assert (await client.get("/api/v1/portfolio")).status_code == 403


async def test_not_connected_state(client, db_session, fake_kite):
    await _member(client, db_session)
    assert (await client.get("/api/v1/portfolio/connection")).json()["status"] == "not_connected"
    resp = await client.get("/api/v1/portfolio")
    assert resp.status_code == 404 and resp.json()["error"]["code"] == "BROKER_NOT_CONNECTED"


async def test_callback_connects_and_stores_token_encrypted(client, db_session, fake_kite):
    user, _ = await _member(client, db_session)
    body = await _connect(client, fake_kite)
    assert body["status"] == "connected"
    assert SECRET_TOKEN not in str(body) and "AB1234" not in str(body)
    stored = (await db_session.execute(
        text("SELECT access_token FROM broker_connections WHERE user_id = :u"), {"u": str(user.id)})).scalar_one()
    assert stored and stored != SECRET_TOKEN and SECRET_TOKEN not in stored  # ciphertext, not plaintext


async def test_invalid_request_token_is_rejected(client, db_session, fake_kite):
    await _member(client, db_session)
    resp = await _callback(client, state=await _start(client), request_token="bad")
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "BROKER_AUTH_FAILED"
    malformed = "../../x<script>"
    resp = await _callback(client, state=await _start(client), request_token=malformed)
    assert resp.status_code == 400 and malformed not in resp.text  # never echoed back


async def test_portfolio_returns_normalized_holdings_positions_and_summary(client, db_session, fake_kite):
    await _member(client, db_session)
    await _connect(client, fake_kite)
    resp = await client.get("/api/v1/portfolio")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [h["trading_symbol"] for h in body["holdings"]] == ["INFY", "TCS"]
    assert [p["trading_symbol"] for p in body["positions"]] == ["NIFTY24OCTFUT"]  # closed SBIN dropped
    assert body["summary"]["current_value"] == 24900.0 and body["summary"]["pnl"] == 1900.0
    assert fake_kite.tokens_seen[-1] == SECRET_TOKEN  # decrypted only in memory, for the broker call
    assert SECRET_TOKEN not in resp.text and "AB1234" not in resp.text
    assert not (_walk_keys(body) & {"access_token", "kite_user_id", "api_secret", "request_token", "user_id"})
    info = (await client.get("/api/v1/portfolio/connection")).json()
    assert info["status"] == "connected" and info["last_synced_at"]
    assert info["last_synced_at"].endswith(("Z", "+00:00")) and body["last_synced_at"].endswith(("Z", "+00:00"))
    assert set(info) == {"broker", "status", "connected_at", "last_synced_at"}


async def test_empty_broker_account(client, db_session, fake_kite):
    await _member(client, db_session)
    await _connect(client, fake_kite)
    fake_kite.holdings, fake_kite.positions = [], []
    body = (await client.get("/api/v1/portfolio")).json()
    assert body["holdings"] == [] and body["summary"]["holdings_count"] == 0 and body["summary"]["current_value"] is None


async def test_expired_session_marks_connection_for_reconnect(client, db_session, fake_kite):
    user, _ = await _member(client, db_session)
    await _connect(client, fake_kite)
    fake_kite.error = BrokerSessionExpiredError("expired")
    resp = await client.get("/api/v1/portfolio")
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "BROKER_SESSION_EXPIRED"
    row = (await db_session.execute(text(
        "SELECT status, access_token FROM broker_connections WHERE user_id = :u"), {"u": str(user.id)})).one()
    assert row.status == "error" and row.access_token is None
    assert (await client.get("/api/v1/portfolio/connection")).json()["status"] == "error"
    # Reconnecting restores access on the same row.
    fake_kite.error = None
    await _connect(client, fake_kite)
    assert (await client.get("/api/v1/portfolio")).status_code == 200
    n = (await db_session.execute(text(
        "SELECT COUNT(*) FROM broker_connections WHERE user_id = :u"), {"u": str(user.id)})).scalar_one()
    assert n == 1


async def test_transient_broker_failure_keeps_connection(client, db_session, fake_kite):
    user, _ = await _member(client, db_session)
    await _connect(client, fake_kite)
    fake_kite.error = BrokerConnectionError("network")
    resp = await client.get("/api/v1/portfolio")
    assert resp.status_code == 502 and resp.json()["error"]["code"] == "BROKER_AUTH_FAILED"
    assert (await client.get("/api/v1/portfolio/connection")).json()["status"] == "connected"


async def test_disconnect_clears_token_and_requires_csrf(client, db_session, fake_kite):
    user, headers = await _member(client, db_session)
    await _connect(client, fake_kite)
    assert (await client.delete("/api/v1/portfolio/zerodha")).status_code == 403  # no CSRF header
    assert (await client.delete("/api/v1/portfolio/zerodha", headers=headers)).status_code == 204
    row = (await db_session.execute(text(
        "SELECT status, access_token FROM broker_connections WHERE user_id = :u"), {"u": str(user.id)})).one()
    assert row.status == "disconnected" and row.access_token is None
    assert (await client.get("/api/v1/portfolio")).status_code == 404


async def test_other_users_cannot_see_my_portfolio(client, db_session, fake_kite):
    owner, _ = await _member(client, db_session)
    await _connect(client, fake_kite)
    other, _ = await _member(client, db_session)
    # The other member only ever sees their own (absent) connection — no id parameter exists to ask for mine.
    assert (await client.get("/api/v1/portfolio")).status_code == 404
    assert (await client.get("/api/v1/portfolio/connection")).json()["status"] == "not_connected"
    assert (await client.get(f"/api/v1/portfolio?user_id={owner.id}")).status_code == 404
    username = (await db_session.execute(text(
        "SELECT username FROM profiles WHERE user_id = :u"), {"u": str(owner.id)})).scalar_one()
    profile = (await client.get(f"/api/v1/profile/{username}")).text
    for leaked in ("INFY", "TCS", "AB1234", "holdings", "broker", "kite", "pnl"):
        assert leaked.lower() not in profile.lower(), leaked


# ---------------------------------------------------------------------------
# Compliance
# ---------------------------------------------------------------------------

def test_no_trading_or_account_modifying_routes_exist():
    forbidden = ("order", "trade", "buy", "sell", "gtt", "modify", "convert", "basket", "margin", "mutual")
    portfolio_routes = [(path, sorted(m.upper() for m in ops)) for path, ops in app.openapi()["paths"].items()
                        if "/portfolio" in path]
    assert portfolio_routes
    for path, methods in portfolio_routes:
        assert not any(word in path.lower() for word in forbidden), path
    write_routes = [(p, m) for p, m in portfolio_routes if set(m) & {"POST", "PUT", "PATCH"}]
    # The only write is completing our own OAuth login; disconnect deletes only Qfinera's stored record.
    assert write_routes == [("/api/v1/portfolio/zerodha/callback", ["POST"])]


def test_portfolio_response_carries_no_recommendation_fields():
    from app.modules.portfolio.schemas import HoldingItem, PortfolioResponse, PortfolioSummary
    words = ("recommend", "signal", "target", "action", "buy", "sell", "hold_", "rating")
    for model in (HoldingItem, PortfolioSummary, PortfolioResponse):
        for name in model.model_fields:
            assert not any(w in name.lower() for w in words), (model.__name__, name)



# ---------------------------------------------------------------------------
# OAuth state
# ---------------------------------------------------------------------------

async def test_state_is_random_and_carries_no_identity(client, db_session, fake_kite):
    user, _ = await _member(client, db_session)
    states = {await _start(client) for _ in range(5)}
    assert len(states) == 5 and all(len(s_) >= 43 for s_ in states)  # 32 random bytes, urlsafe
    for s_ in states:
        assert str(user.id) not in s_ and user.email not in s_


async def test_missing_and_invalid_state_rejected(client, db_session, fake_kite):
    user, _ = await _member(client, db_session)
    await _start(client)
    for state in (None, "", "not-a-real-state", "x" * 500):
        resp = await _callback(client, state=state)
        assert resp.status_code == 400 and resp.json()["error"]["code"] == "BROKER_STATE_INVALID", state
    assert (await client.get("/api/v1/portfolio/connection")).json()["status"] == "not_connected"


async def test_expired_state_rejected(client, db_session, fake_kite):
    await _member(client, db_session)
    state = await _start(client)
    await oauth_state._redis.delete(oauth_state._PREFIX + oauth_state._digest(state))  # TTL elapsed
    assert (await _callback(client, state=state)).json()["error"]["code"] == "BROKER_STATE_INVALID"
    assert oauth_state.STATE_TTL_SECONDS <= 900


async def test_state_is_single_use(client, db_session, fake_kite):
    await _member(client, db_session)
    state = await _start(client)
    assert (await _callback(client, state=state)).status_code == 200
    assert (await _callback(client, state=state)).json()["error"]["code"] == "BROKER_STATE_INVALID"


async def test_state_from_another_user_is_rejected_and_burned(client, db_session, fake_kite):
    victim, _ = await _member(client, db_session)
    attacker, _ = await _member(client, db_session)
    attacker_state = await _start(client)  # attacker starts a login…
    await _login(client, victim)  # …and lures the victim's session into completing it
    resp = await _callback(client, state=attacker_state)
    assert resp.json()["error"]["code"] == "BROKER_STATE_INVALID"
    for uid in (victim.id, attacker.id):
        n = (await db_session.execute(text(
            "SELECT COUNT(*) FROM broker_connections WHERE user_id = :u"), {"u": str(uid)})).scalar_one()
        assert n == 0
    await _login(client, attacker)
    assert (await _callback(client, state=attacker_state)).json()["error"]["code"] == "BROKER_STATE_INVALID"  # burned


async def test_state_from_another_session_of_same_user_is_rejected(client, db_session, fake_kite):
    user, _ = await _member(client, db_session)
    state = await _start(client)
    await _login(client, user)  # new session for the same account
    assert (await _callback(client, state=state)).json()["error"]["code"] == "BROKER_STATE_INVALID"


async def test_callback_requires_csrf_and_old_get_route_is_gone(client, db_session, fake_kite):
    await _member(client, db_session)
    state = await _start(client)
    resp = await client.post("/api/v1/portfolio/zerodha/callback", json={"request_token": "abc123", "state": state})
    assert resp.status_code == 403
    assert (await client.get("/api/v1/portfolio/zerodha/callback?request_token=abc123")).status_code == 405


# ---------------------------------------------------------------------------
# request_token never leaks
# ---------------------------------------------------------------------------

async def test_request_token_never_logged_or_returned(client, db_session, fake_kite, caplog):
    caplog.set_level(logging.DEBUG)
    await _member(client, db_session)
    token = "ReqTok9f8e7d6c5b4a"
    ok = await _callback(client, state=await _start(client), request_token=token)
    bad_state = await _callback(client, state="forged", request_token=token)
    fake_kite.error = None
    for resp in (ok, bad_state):
        assert token not in resp.text
    assert token not in caplog.text and SECRET_TOKEN not in caplog.text
    portfolio = await client.get("/api/v1/portfolio")
    assert token not in portfolio.text and SECRET_TOKEN not in portfolio.text


# ---------------------------------------------------------------------------
# Broker token encryption
# ---------------------------------------------------------------------------

def _fernet(secret: str) -> Fernet:
    return crypto._derive_fernet(secret)


async def test_broker_token_uses_broker_key_not_ai_key(client, db_session, fake_kite):
    user, _ = await _member(client, db_session)
    await _connect(client, fake_kite)
    stored = (await db_session.execute(
        text("SELECT access_token FROM broker_connections WHERE user_id = :u"), {"u": str(user.id)})).scalar_one()
    assert _fernet("test-broker-key-0123456789").decrypt(stored.encode()).decode() == SECRET_TOKEN
    with pytest.raises(Exception):
        _fernet("test-ai-key-0123456789").decrypt(stored.encode())


def test_ai_key_encryption_is_unchanged():
    ciphertext = crypto.encrypt_secret("sk-ai-key")
    assert crypto.decrypt_secret(ciphertext) == "sk-ai-key"
    assert _fernet("test-ai-key-0123456789").decrypt(ciphertext.encode()).decode() == "sk-ai-key"


async def test_legacy_ai_key_encrypted_token_is_read_then_reencrypted(client, db_session, fake_kite):
    user, _ = await _member(client, db_session)
    await _connect(client, fake_kite)
    legacy = _fernet("test-ai-key-0123456789").encrypt(SECRET_TOKEN.encode()).decode()
    await db_session.execute(text("UPDATE broker_connections SET access_token = :t WHERE user_id = :u"),
                             {"t": legacy, "u": str(user.id)})
    await db_session.flush()
    assert (await client.get("/api/v1/portfolio")).status_code == 200
    assert fake_kite.tokens_seen[-1] == SECRET_TOKEN
    stored = (await db_session.execute(
        text("SELECT access_token FROM broker_connections WHERE user_id = :u"), {"u": str(user.id)})).scalar_one()
    assert stored != legacy
    assert _fernet("test-broker-key-0123456789").decrypt(stored.encode()).decode() == SECRET_TOKEN


async def test_connect_fails_cleanly_without_broker_key(client, db_session, fake_kite, monkeypatch):
    user, _ = await _member(client, db_session)
    monkeypatch.setattr(settings, "BROKER_TOKEN_ENCRYPTION_SECRET", None)
    resp = await _callback(client, state=await _start(client))
    assert resp.status_code == 503 and resp.json()["error"]["code"] == "BROKER_NOT_CONFIGURED"
    n = (await db_session.execute(text(
        "SELECT COUNT(*) FROM broker_connections WHERE user_id = :u"), {"u": str(user.id)})).scalar_one()
    assert n == 0  # nothing stored, certainly not plaintext


# ---------------------------------------------------------------------------
# Quantity
# ---------------------------------------------------------------------------

def test_collateral_quantity_is_not_added_to_holding_quantity():
    """Kite documents `quantity` as realised (T+2) and `t1_quantity`
    separately; `collateral_quantity` is only 'quantity used as collateral',
    with no documented relationship to `quantity`. We count settled + T+1
    and never add collateral, to avoid a possible double count."""
    raw = dict(KITE_HOLDINGS[0], quantity=10, t1_quantity=2, collateral_quantity=5)
    assert portfolio_service.normalize_holding(raw)["quantity"] == 12
