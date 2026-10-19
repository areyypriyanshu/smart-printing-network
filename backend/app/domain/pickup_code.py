import secrets

PICKUP_CODE_LENGTH = 6
PICKUP_CODE_SPACE = 10**PICKUP_CODE_LENGTH


def generate_pickup_code() -> str:
    return f"{secrets.randbelow(PICKUP_CODE_SPACE):0{PICKUP_CODE_LENGTH}d}"


def verify_pickup_code(expected: str, submitted: str) -> bool:
    """Compare a submitted pickup code with the stored one.

    The comparison is constant time so it does not leak how many leading
    digits were correct. The code is short enough to be guessed, so the
    real protection against guessing is the attempt limit, not this function.
    """
    return secrets.compare_digest(expected, submitted)
