"""A shared absolute time limit for every network operation in a build search."""
import time


def remaining(deadline, maximum):
    if deadline is None:
        return maximum
    seconds = deadline - time.monotonic()
    if seconds <= 0:
        raise TimeoutError('Время поиска по площадкам истекло')
    return min(maximum, seconds)


def request_timeout(deadline):
    return (remaining(deadline, 3), remaining(deadline, 5))
