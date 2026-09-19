import cv2


def screen_stability(first, second, threshold: float = 2.5) -> tuple[bool, float]:
    if first.normalized.shape != second.normalized.shape:
        return False, float("inf")
    difference = float(cv2.cvtColor(cv2.absdiff(first.normalized, second.normalized), cv2.COLOR_BGR2GRAY).mean())
    return difference <= threshold, difference
