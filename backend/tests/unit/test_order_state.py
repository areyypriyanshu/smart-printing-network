from app.domain.order_state import (
    ACCEPTED,
    ALL_STATUSES,
    ALLOWED_ACTORS,
    CANCELLED,
    COLLECTED,
    EXPIRED,
    PAID,
    PENDING_PAYMENT,
    PRINTING,
    READY,
    REJECTED,
    RESERVED,
    TERMINAL,
    allowed_actors,
    can_actor_transition,
    can_transition,
    is_active,
    is_terminal,
)
from hypothesis import given
from hypothesis import strategies as st

# Every order is booked as RESERVED and paid in cash at the counter.
# PENDING_PAYMENT and PAID remain because rows written by the previous
# online-payment version still have to be read, expired and worked.
EXPECTED_ALLOWED = {
    PENDING_PAYMENT: {EXPIRED, CANCELLED},
    PAID: {ACCEPTED, REJECTED, CANCELLED},
    RESERVED: {ACCEPTED, REJECTED, CANCELLED, EXPIRED},
    ACCEPTED: {PRINTING, CANCELLED},
    PRINTING: {READY},
    READY: {COLLECTED, EXPIRED},
}


def test_transition_table_matches_the_specification() -> None:
    for from_status in ALL_STATUSES:
        for to_status in ALL_STATUSES:
            expected = to_status in EXPECTED_ALLOWED.get(from_status, set())
            assert can_transition(from_status, to_status) is expected, (
                f"{from_status} -> {to_status}"
            )


def test_terminal_statuses_have_no_outgoing_transitions() -> None:
    for status in TERMINAL:
        for target in ALL_STATUSES:
            assert not can_transition(status, target)


def test_unknown_status_allows_nothing() -> None:
    assert not can_transition("NOPE", PAID)
    assert allowed_actors("NOPE", PAID) == frozenset()


def test_nothing_can_mark_an_order_paid_any_more() -> None:
    """The money is taken at the counter, not by a provider callback."""
    for from_status in ALL_STATUSES:
        assert not can_transition(from_status, PAID), from_status
        assert not can_transition(from_status, PENDING_PAYMENT), from_status


def test_only_the_system_can_expire_an_order() -> None:
    assert can_actor_transition("system", PENDING_PAYMENT, EXPIRED)
    assert can_actor_transition("system", RESERVED, EXPIRED)
    for actor in ("customer", "vendor"):
        assert not can_actor_transition(actor, PENDING_PAYMENT, EXPIRED)
        assert not can_actor_transition(actor, RESERVED, EXPIRED)


def test_the_webhook_actor_is_gone() -> None:
    for from_status in ALL_STATUSES:
        for to_status in ALL_STATUSES:
            assert not can_actor_transition("webhook", from_status, to_status)


def test_customer_can_cancel_before_acceptance_only() -> None:
    assert can_actor_transition("customer", PENDING_PAYMENT, CANCELLED)
    assert can_actor_transition("customer", PAID, CANCELLED)
    assert can_actor_transition("customer", RESERVED, CANCELLED)
    assert not can_actor_transition("customer", ACCEPTED, CANCELLED)
    assert not can_actor_transition("customer", PRINTING, READY)


def test_vendor_drives_the_printing_lifecycle() -> None:
    assert can_actor_transition("vendor", PAID, ACCEPTED)
    assert can_actor_transition("vendor", PAID, REJECTED)
    assert can_actor_transition("vendor", RESERVED, ACCEPTED)
    assert can_actor_transition("vendor", RESERVED, REJECTED)
    assert can_actor_transition("vendor", ACCEPTED, PRINTING)
    assert can_actor_transition("vendor", ACCEPTED, CANCELLED)
    assert can_actor_transition("vendor", PRINTING, READY)
    assert can_actor_transition("vendor", READY, COLLECTED)


def test_every_allowed_transition_has_at_least_one_actor() -> None:
    for from_status, targets in EXPECTED_ALLOWED.items():
        for to_status in targets:
            assert allowed_actors(from_status, to_status), (from_status, to_status)


def test_actor_map_only_covers_allowed_transitions() -> None:
    for (from_status, to_status), actors in ALLOWED_ACTORS.items():
        assert can_transition(from_status, to_status)
        assert actors


def test_active_and_terminal_statuses_do_not_overlap() -> None:
    assert not is_active(COLLECTED)
    assert is_active(PAID)
    assert is_active(RESERVED)
    assert is_terminal(REJECTED)
    assert not is_terminal(RESERVED)
    assert not is_terminal(PRINTING)


@given(st.lists(st.sampled_from(sorted(ALL_STATUSES)), max_size=25))
def test_random_transition_attempts_never_reach_an_invalid_state(targets: list[str]) -> None:
    status = RESERVED
    for target in targets:
        if can_transition(status, target):
            status = target
        assert status in ALL_STATUSES
    if is_terminal(status):
        assert not any(can_transition(status, target) for target in ALL_STATUSES)


def test_a_cash_order_can_never_be_marked_paid() -> None:
    assert not can_transition(RESERVED, PAID)
    assert not can_actor_transition("vendor", RESERVED, PAID)


def test_the_only_transition_out_of_reserved_a_customer_can_make_is_cancellation() -> None:
    """The customer booked the job; they may call it off, nothing else."""
    for target in ALL_STATUSES:
        if target == CANCELLED:
            assert can_actor_transition("customer", RESERVED, target)
        else:
            assert not can_actor_transition("customer", RESERVED, target), target


def test_the_shop_and_the_system_drive_a_reserved_order_forward() -> None:
    assert can_actor_transition("vendor", RESERVED, ACCEPTED)
    assert can_actor_transition("vendor", RESERVED, REJECTED)
    assert can_actor_transition("vendor", RESERVED, CANCELLED)
    assert can_actor_transition("system", RESERVED, REJECTED)
    assert can_actor_transition("system", RESERVED, EXPIRED)
