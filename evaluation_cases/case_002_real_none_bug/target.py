def get_name(user: dict[str, str | None]) -> str:
    """Return a trimmed name or an empty string when name is absent."""
    return user.get("name").strip()
