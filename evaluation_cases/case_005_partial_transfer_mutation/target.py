def transfer_balance(
    source: dict[str, int],
    target: dict[str, int],
    amount: int,
) -> None:
    """Transfer atomically; failure must not partially mutate accounts."""
    source["balance"] -= amount
    target["balance"] += amount
