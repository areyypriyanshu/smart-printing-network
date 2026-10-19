import uuid

from pydantic import BaseModel


class SimulatePaymentRequest(BaseModel):
    order_id: uuid.UUID
