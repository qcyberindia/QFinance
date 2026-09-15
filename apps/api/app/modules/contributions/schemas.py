from datetime import datetime

from pydantic import BaseModel


class CreditLedgerEntryResponse(BaseModel):
    amount_paise: int
    reason: str
    created_at: datetime

    class Config:
        from_attributes = True


class CreditsSummaryResponse(BaseModel):
    balance_paise: int
    entries: list[CreditLedgerEntryResponse]
    page: int
    page_size: int
    total: int
