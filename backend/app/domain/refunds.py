"""Pure rules for refunds.

Kept in the domain layer because the backoff schedule is a business rule,
not a job detail: it decides how long a customer waits for their money
back, and it has to be the same everywhere it is used.
"""

from typing import Final

MAX_BACKOFF_MINUTES: Final = 60
FIRST_BACKOFF_MINUTES: Final = 1


def refund_backoff_minutes(attempts: int) -> int:
    """Minutes to wait before the next refund attempt.

    One, two, four, eight, sixteen minutes, then doubling up to a cap of
    one hour. `attempts` is the number of attempts already made, so the
    first retry waits one minute.
    """
    if attempts < 1:
        return FIRST_BACKOFF_MINUTES
    return min(FIRST_BACKOFF_MINUTES * int(2 ** max(attempts - 1, 0)), MAX_BACKOFF_MINUTES)


def refund_backoff_seconds(attempts: int) -> int:
    return refund_backoff_minutes(attempts) * 60
