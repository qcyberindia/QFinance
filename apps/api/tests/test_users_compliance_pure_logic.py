"""DB-free unit test for the one deterministic, non-DB piece of users/service.py's
compliance-acknowledgment logic: the allowed risk-disclosure context values
(CMPL-005 — "at signup and at first payment", API Spec §4.5.2). The two
acknowledge_* functions themselves write to the database (INSERT +
commit) and are therefore integration-only — see
test_community_integration.py's compliance-acknowledgment stubs.

STATUS: reproduced verbatim in an isolated sandbox and run with real pytest.
"""
from app.modules.users.service import VALID_RISK_DISCLOSURE_CONTEXTS


def test_risk_disclosure_contexts_match_the_two_prd_required_occasions():
    """CMPL-005's exact wording: 'at signup and at the point of first
    payment' — exactly these two, no more, no fewer."""
    assert set(VALID_RISK_DISCLOSURE_CONTEXTS) == {"signup", "first_payment"}
    assert len(VALID_RISK_DISCLOSURE_CONTEXTS) == 2
