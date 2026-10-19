from typing import Final

PENDING_PAYMENT: Final = "PENDING_PAYMENT"
PAID: Final = "PAID"
ACCEPTED: Final = "ACCEPTED"
PRINTING: Final = "PRINTING"
READY: Final = "READY"
COLLECTED: Final = "COLLECTED"
REJECTED: Final = "REJECTED"
CANCELLED: Final = "CANCELLED"
EXPIRED: Final = "EXPIRED"

ALL_STATUSES: Final = frozenset(
    {
        PENDING_PAYMENT,
        PAID,
        ACCEPTED,
        PRINTING,
        READY,
        COLLECTED,
        REJECTED,
        CANCELLED,
        EXPIRED,
    }
)

ACTIVE_STATUSES: Final = frozenset({PAID, ACCEPTED, PRINTING, READY})

TERMINAL: Final = frozenset({COLLECTED, REJECTED, CANCELLED, EXPIRED})

REFUNDABLE_FROM: Final = frozenset({PAID, ACCEPTED})

REFUNDABLE_TO: Final = frozenset({REJECTED, CANCELLED})

ALLOWED: Final[dict[str, frozenset[str]]] = {
    PENDING_PAYMENT: frozenset({PAID, EXPIRED, CANCELLED}),
    PAID: frozenset({ACCEPTED, REJECTED, CANCELLED}),
    ACCEPTED: frozenset({PRINTING, CANCELLED}),
    PRINTING: frozenset({READY}),
    READY: frozenset({COLLECTED}),
}

ACTOR_TYPES: Final = frozenset({"customer", "vendor", "system", "webhook"})

ALLOWED_ACTORS: Final[dict[tuple[str, str], frozenset[str]]] = {
    (PENDING_PAYMENT, PAID): frozenset({"webhook"}),
    (PENDING_PAYMENT, EXPIRED): frozenset({"system"}),
    (PENDING_PAYMENT, CANCELLED): frozenset({"customer", "system"}),
    (PAID, ACCEPTED): frozenset({"vendor"}),
    (PAID, REJECTED): frozenset({"vendor", "system"}),
    (PAID, CANCELLED): frozenset({"customer", "system"}),
    (ACCEPTED, PRINTING): frozenset({"vendor"}),
    (ACCEPTED, CANCELLED): frozenset({"vendor"}),
    (PRINTING, READY): frozenset({"vendor"}),
    (READY, COLLECTED): frozenset({"vendor"}),
}


def can_transition(frm: str, to: str) -> bool:
    return to in ALLOWED.get(frm, frozenset())


def allowed_actors(frm: str, to: str) -> frozenset[str]:
    return ALLOWED_ACTORS.get((frm, to), frozenset())


def can_actor_transition(actor_type: str, frm: str, to: str) -> bool:
    return actor_type in allowed_actors(frm, to)


def is_terminal(status: str) -> bool:
    return status in TERMINAL


def is_active(status: str) -> bool:
    return status in ACTIVE_STATUSES


def queues_refund(frm: str, to: str) -> bool:
    """True when a transition means the customer must be refunded.

    Only a rejection or a cancellation of an order that was already paid
    moves money back. Cancelling an unpaid order moves nothing. The
    transition has to be a legal one, so that this agrees with the
    transition table rather than describing a move the state machine
    forbids.
    """
    return can_transition(frm, to) and frm in REFUNDABLE_FROM and to in REFUNDABLE_TO
