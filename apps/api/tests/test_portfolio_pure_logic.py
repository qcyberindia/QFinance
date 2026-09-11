"""DB-free unit tests for portfolio/service.py's adapter-facing pure logic,
and for the REAL `ZerodhaAdapter` class's safe-when-unconfigured behavior
(no database, no real Zerodha credentials, no network — this environment has
neither `ZERODHA_API_KEY` nor `ZERODHA_API_SECRET` set, which is exactly the
condition these tests exercise for real).

Per the explicit instruction ("Do NOT require real Zerodha credentials in the
test suite"), the adapter-injection tests use a FakeBrokerAdapter rather than
the real ZerodhaAdapter — but the unconfigured-safety tests deliberately use
the REAL ZerodhaAdapter class, since that specific behavior (fail safely, no
crash, no real API call attempted) is exactly what's testable without
credentials and is the actual production safety mechanism, not a mock of it.

STATUS: see work_memory.md for the exact EXECUTED/NOT-EXECUTED boundary.
"""
import pytest

from app.core.errors import QFinanceAPIError
from app.integrations.brokers import zerodha as zerodha_module
from app.integrations.brokers.base import BrokerConnectionError, BrokerNotConfiguredError
from app.integrations.brokers.zerodha import ZerodhaAdapter
from app.modules.portfolio import service
from app.modules.portfolio.models import VALID_BROKERS, VALID_CONNECTION_STATUSES


@pytest.fixture
def unconfigured_zerodha(monkeypatch):
    """Test-only isolation fixture — NOT a production-code change.

    `zerodha.py` does `settings = get_settings()` once at module-import time
    (a deliberate, cheap singleton, matching every other integration module
    in this codebase — `payment_service.py`/`email_service.py` do the same).
    That means once the process has started, the developer environment's
    real `.env` values for `ZERODHA_API_KEY`/`ZERODHA_API_SECRET` are already
    baked into that one already-imported `settings` object for the rest of
    the test run — setting/unsetting an env var *during* the test session
    has no effect on it (`get_settings()` is also `@lru_cache`'d, so even
    calling it again wouldn't re-read the environment).

    The 4 tests below need to exercise the 'genuinely unconfigured' branch
    specifically, independent of whatever the developer's local `.env`
    currently contains (including an intentional placeholder value while GUI
    work continues, per the reported root cause) — so this fixture directly
    monkeypatches the two attributes on that specific already-imported
    `settings` object for the duration of one test only. `monkeypatch`
    auto-reverts after the test, so no other test, and nothing about the
    developer's actual `.env` file, is touched or left changed.
    """
    monkeypatch.setattr(zerodha_module.settings, "ZERODHA_API_KEY", None)
    monkeypatch.setattr(zerodha_module.settings, "ZERODHA_API_SECRET", None)


class FakeBrokerAdapter:
    """A minimal fake satisfying the BrokerAdapter protocol by shape, for
    tests that need to control exactly what the adapter returns/raises
    without touching the real ZerodhaAdapter or any network call."""

    def __init__(self, *, login_url=None, raise_not_configured=False, raise_connection_error=False):
        self._login_url = login_url
        self._raise_not_configured = raise_not_configured
        self._raise_connection_error = raise_connection_error

    def get_login_url(self):
        if self._raise_not_configured:
            raise BrokerNotConfiguredError("fake: not configured")
        if self._raise_connection_error:
            raise BrokerConnectionError("fake: connection error")
        return self._login_url

    def exchange_request_token(self, *, request_token):
        raise NotImplementedError

    def fetch_holdings(self, *, access_token):
        raise NotImplementedError

    def fetch_positions(self, *, access_token):
        raise NotImplementedError


# ---------------------------------------------------------------------------
# models.py constants match the locked DB Schema V2 CHECK constraints
# ---------------------------------------------------------------------------

def test_valid_brokers_matches_db_check_constraint():
    """CHECK (broker = 'zerodha') — single value in MVP, per Database Schema
    V2 §1's explicit 'MVP: single value, extensible later' comment."""
    assert VALID_BROKERS == ("zerodha",)


def test_valid_connection_statuses_matches_db_check_constraint():
    assert set(VALID_CONNECTION_STATUSES) == {"connected", "disconnected", "error"}


# ---------------------------------------------------------------------------
# service.get_login_url — the one fully DB-free service function (no `db`
# parameter at all), genuinely unit-testable end-to-end
# ---------------------------------------------------------------------------

async def test_get_login_url_returns_the_adapters_url():
    fake = FakeBrokerAdapter(login_url="https://kite.zerodha.com/connect/login?v=3&api_key=fake")
    url = await service.get_login_url(adapter=fake)
    assert url == "https://kite.zerodha.com/connect/login?v=3&api_key=fake"


async def test_get_login_url_translates_not_configured_to_503():
    """Direct test of the PF.1-documented BROKER_NOT_CONFIGURED translation —
    the actual error-code contract from API Specification V2 §7, exercised
    against the real service.py function, not just read."""
    fake = FakeBrokerAdapter(raise_not_configured=True)
    with pytest.raises(QFinanceAPIError) as exc_info:
        await service.get_login_url(adapter=fake)
    assert exc_info.value.code == "BROKER_NOT_CONFIGURED"
    assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# The REAL ZerodhaAdapter's safe-when-unconfigured behavior — no fake here,
# no credentials needed, exercises the production class directly
# ---------------------------------------------------------------------------

def test_real_zerodha_adapter_raises_not_configured_for_login_url_with_no_credentials(unconfigured_zerodha):
    """Explicitly isolated via the `unconfigured_zerodha` fixture (see its
    docstring) rather than relying on this environment's ambient
    ZERODHA_API_KEY/ZERODHA_API_SECRET state, which may legitimately be a
    real (even if placeholder) value while broker GUI work continues in
    parallel. This is the fix for the test-isolation bug reported against
    the previous version of this test, which relied on ambient state instead
    of asserting it."""
    adapter = ZerodhaAdapter()
    with pytest.raises(BrokerNotConfiguredError):
        adapter.get_login_url()


def test_real_zerodha_adapter_raises_not_configured_for_fetch_holdings_with_no_credentials(unconfigured_zerodha):
    adapter = ZerodhaAdapter()
    with pytest.raises(BrokerNotConfiguredError):
        adapter.fetch_holdings(access_token="irrelevant-not-reached")


def test_real_zerodha_adapter_raises_not_configured_for_fetch_positions_with_no_credentials(unconfigured_zerodha):
    adapter = ZerodhaAdapter()
    with pytest.raises(BrokerNotConfiguredError):
        adapter.fetch_positions(access_token="irrelevant-not-reached")


def test_real_zerodha_adapter_raises_not_configured_for_exchange_request_token_with_no_credentials(unconfigured_zerodha):
    """This is also the direct regression test for PHASE 3's requirement
    #9 ('handle missing broker configuration safely') applied to the
    callback path specifically — the most security-sensitive of the four
    adapter methods, since it's the one that would otherwise attempt to
    exchange a real token."""
    adapter = ZerodhaAdapter()
    with pytest.raises(BrokerNotConfiguredError):
        adapter.exchange_request_token(request_token="irrelevant-not-reached")


def test_zerodha_adapter_is_structurally_read_only():
    """Characterization test for BOUND-001's structural enforcement: confirm
    the real ZerodhaAdapter class exposes exactly the 4 read/connect-only
    methods the BrokerAdapter protocol defines, and nothing with an
    order/trade/modify-shaped name — if someone ever adds a `place_order` or
    `modify_position` method to this class, this test fails immediately."""
    public_methods = {name for name in dir(ZerodhaAdapter) if not name.startswith("_")}
    assert public_methods == {"get_login_url", "exchange_request_token", "fetch_holdings", "fetch_positions"}
    forbidden_substrings = ("order", "trade", "buy", "sell", "modify", "execute", "place")
    for method_name in public_methods:
        for forbidden in forbidden_substrings:
            assert forbidden not in method_name.lower(), (
                f"ZerodhaAdapter.{method_name} contains forbidden substring '{forbidden}' — "
                "BOUND-001 requires this adapter to remain structurally read-only."
            )
