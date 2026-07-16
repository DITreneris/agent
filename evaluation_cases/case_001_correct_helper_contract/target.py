def safe_parse(value: str) -> int | None:
    if not value:
        return None
    return int(value)


def parse_optional_age(raw: str) -> int | None:
    return safe_parse(raw)
