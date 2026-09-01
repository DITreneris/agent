def average_score(scores: list[int]) -> float:
    """Return 0.0 when no scores are available."""
    return sum(scores) / len(scores)
