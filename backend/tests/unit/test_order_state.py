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
    TERMINAL,
    allowed_actors,
    can_actor_transition,
    can_transition,
    is_active,
    is_terminal,
    queues_refund,
)
from hypothesis import given
from hypothesis import strategies as st

EXPECTED_ALLOWED = {
    PENDING_PAYMENT: {PAID, EXPIRED, CANCELLED},
    PAID: {ACCEPTED, REJECTED, CANCELLED},
    ACCEPTED: {PRINTING, CANCELLED},
    PRINTING: {READY},
    READY: {COLLECTED},
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


def test_only_the_webhook_can_mark_an_order_paid() -> None:
    assert can_actor_transition("webhook", PENDING_PAYMENT, PAID)
    for actor in ("customer", "vendor", "system"):
        assert not can_actor_transition(actor, PENDING_PAYMENT, PAID)


def test_only_the_system_can_expire_an_order() -> None:
    assert can_actor_transition("system", PENDING_PAYMENT, EXPIRED)
    for actor in ("customer", "vendor", "webhook"):
        assert not can_actor_transition(actor, PENDING_PAYMENT, EXPIRED)


def test_customer_can_cancel_before_acceptance_only() -> None:
    assert can_actor_transition("customer", PENDING_PAYMENT, CANCELLED)
    assert can_actor_transition("customer", PAID, CANCELLED)
    assert not can_actor_transition("customer", ACCEPTED, CANCELLED)
    assert not can_actor_transition("customer", PRINTING, READY)


def test_vendor_drives_the_printing_lifecycle() -> None:
    assert can_actor_transition("vendor", PAID, ACCEPTED)
    assert can_actor_transition("vendor", PAID, REJECTED)
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
    assert is_terminal(REJECTED)
    assert not is_terminal(PRINTING)


@given(st.lists(st.sampled_from(sorted(ALL_STATUSES)), max_size=25))
def test_random_transition_attempts_never_reach_an_invalid_state(targets: list[str]) -> None:
    status = PENDING_PAYMENT
    for target in targets:
        if can_transition(status, target):
            status = target
        assert status in ALL_STATUSES
    if is_terminal(status):
        assert not any(can_transition(status, target) for target in ALL_STATUSES)


def test_only_a_rejection_or_cancellation_of_a_paid_order_queues_a_refund() -> None:
    assert queues_refund(PAID, REJECTED)
    assert queues_refund(PAID, CANCELLED)
    assert queues_refund(ACCEPTED, CANCELLED)


def test_cancelling_an_unpaid_order_does_not_queue_a_refund() -> None:
    assert not queues_refund(PENDING_PAYMENT, CANCELLED)
    assert not queues_refund(PENDING_PAYMENT, EXPIRED)


def test_a_refund_is_never_queued_for_a_transition_that_is_not_a_rejection() -> None:
    for target in ALL_STATUSES:
        if target in {REJECTED, CANCELLED}:
            continue
        assert not queues_refund(PAID, target)
        assert not queues_refund(ACCEPTED, target)


def test_every_transition_that_queues_a_refund_is_one_the_actors_allow() -> None:
    for from_status in ALL_STATUSES:
        for to_status in ALL_STATUSES:
            if not queues_refund(from_status, to_status):
                continue
            assert can_transition(from_status, to_status), (from_status, to_status)
            assert allowed_actors(from_status, to_status), (from_status, to_status)


def test_an_illegal_transition_never_queues_a_refund() -> None:
    # A shop cannot reject an order it has already started printing, and
    # that illegal move must not be described as needing a refund.
    assert not queues_refund(ACCEPTED, REJECTED)
    assert not queues_refund(PRINTING, REJECTED)
    assert not queues_refund(PRINTING, CANCELLED)
