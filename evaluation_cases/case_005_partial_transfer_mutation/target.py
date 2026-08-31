def transfer_balance(
    source: dict[str, int],
    target: dict[str, int],
    amount: int,
) -> None:
    source["balance"] -= amount
    target["balance"] += amount
