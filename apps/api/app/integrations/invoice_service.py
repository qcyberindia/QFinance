"""InvoiceService / TaxService — Architecture §4.4 provider abstractions, PAY-005/OD-16.

OD-16 (GST/HSN-SAC tax treatment) is explicitly listed in work_memory.md Part E as
"architecturally prepared for but not finalized" — `calculate_tax` below returns 0
unconditionally and is documented as a placeholder, not a real tax computation. Do
not read a `0` result as "GST-exempt" or any other legal conclusion; it means "not
yet implemented," full stop. `tax_treatment_version` is left `None` for the same
reason — there is no version to record yet.

WRITTEN, NOT EXECUTED.
"""


def calculate_tax(amount_paise: int) -> int:
    """PLACEHOLDER — OD-16 pending legal/accounting sign-off on GST/HSN-SAC treatment.
    Always returns 0. Replace this function's body (not its callers) once OD-16 is
    resolved — every other module already reads `tax_paise` from the `invoices` row
    it produces, so no other code needs to change when this is implemented for real."""
    return 0


def build_invoice_fields(*, amount_paise: int, billing_period: str, gateway_reference: str) -> dict:
    """Assembles the fields `billing.service` needs to construct an `Invoice` row —
    kept as a small pure function here (not inlined in billing/service.py) so the
    tax-treatment boundary stays in one place, per Architecture §4.4's abstraction
    intent, even though today it's a trivial pass-through plus a zero."""
    return {
        "amount_paise": amount_paise,
        "tax_paise": calculate_tax(amount_paise),
        "billing_period": billing_period,
        "gateway_reference": gateway_reference,
        "tax_treatment_version": None,
    }
