from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_customer
from app.models import User
from app.rate_limit import user_rate_limit
from app.schemas.quote import QuoteRequest, QuoteResponse
from app.services import quote_service

router = APIRouter(tags=["quotes"])


@router.post(
    "/quotes",
    response_model=QuoteResponse,
    dependencies=[Depends(user_rate_limit(60, 60, "quotes"))],
)
def create_quote(
    body: QuoteRequest,
    user: User = Depends(get_customer),
    session: Session = Depends(get_db),
) -> QuoteResponse:
    return quote_service.quote(session, customer_id=user.id, request=body)
