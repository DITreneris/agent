def find_discount(code: str) -> int | None:
    discounts = {"SAVE10": 10, "SAVE20": 20}
    return discounts.get(code)


def calculate_discount(code: str) -> int:
    discount = find_discount(code)
    return discount if discount is not None else 0
