from typing import Final

PENDING_PAYMENT: Final = "PENDING_PAYMENT"
PAID: Final = "PAID"
RESERVED: Final = "RESERVED"
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
        RESERVED,
        ACCEPTED,
        PRINTING,
        READY,
        COLLECTED,
        REJECTED,
        CANCELLED,
        EXPIRED,
    }
)

# A reserved order is one the customer booked and will pay for in cash at
# the counter. It is active: the shop has work to do, and it is not
# terminal: the job has not been handed over yet.
ACTIVE_STATUSES: Final = frozenset({PAID, RESERVED, ACCEPTED, PRINTING, READY})

TERMINAL: Final = frozenset({COLLECTED, REJECTED, CANCELLED, EXPIRED})

# New orders are always reserved. PAID and PENDING_PAYMENT are kept so
# that an order booked by an earlier version of the application can still
# be read, worked by its shop, or cancelled. No new order enters either
# state, and nothing can move an order into PAID.
ALLOWED: Final[dict[str, frozenset[str]]] = {
    PENDING_PAYMENT: frozenset({EXPIRED, CANCELLED}),
    PAID: frozenset({ACCEPTED, REJECTED, CANCELLED}),
    RESERVED: frozenset({ACCEPTED, REJECTED, CANCELLED, EXPIRED}),
    ACCEPTED: frozenset({PRINTING, CANCELLED}),
    PRINTING: frozenset({READY}),
    READY: frozenset({COLLECTED, EXPIRED}),
}

ACTOR_TYPES: Final = frozenset({"customer", "vendor", "system"})

ALLOWED_ACTORS: Final[dict[tuple[str, str], frozenset[str]]] = {
    (PENDING_PAYMENT, EXPIRED): frozenset({"system"}),
    (PENDING_PAYMENT, CANCELLED): frozenset({"customer", "system"}),
    (PAID, ACCEPTED): frozenset({"vendor"}),
    (PAID, REJECTED): frozenset({"vendor", "system"}),
    (PAID, CANCELLED): frozenset({"customer", "system"}),
    (RESERVED, ACCEPTED): frozenset({"vendor"}),
    (RESERVED, REJECTED): frozenset({"vendor", "system"}),
    (RESERVED, CANCELLED): frozenset({"customer", "vendor", "system"}),
    (RESERVED, EXPIRED): frozenset({"system"}),
    (ACCEPTED, PRINTING): frozenset({"vendor"}),
    (ACCEPTED, CANCELLED): frozenset({"vendor"}),
    (PRINTING, READY): frozenset({"vendor"}),
    (READY, COLLECTED): frozenset({"vendor"}),
    (READY, EXPIRED): frozenset({"system"}),
}

# The statuses a shop may see. An order becomes the shop's once the
# customer has reserved it to pay in cash at the counter, and it stays
# visible afterwards so the shop can look at the history of a job it
# worked on. PAID is kept for orders booked by an earlier version. An
# order that is still waiting for an online payment, or that expired
# before anybody paid, was never the shop's.
SHOP_VISIBLE_STATUSES: Final = frozenset(
    {RESERVED, PAID, ACCEPTED, PRINTING, READY, COLLECTED, REJECTED, CANCELLED}
)


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
