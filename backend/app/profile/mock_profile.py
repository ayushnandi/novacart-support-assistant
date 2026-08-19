MOCK_PROFILES = {
    "ayush": {
        "name": "Ayush",
        "membership_tier": "NovaCart Plus",
        "last_order_id": "NC-10234",
        "city": "Pune",
    },
    "demo": {
        "name": "Demo User",
        "membership_tier": "Standard",
        "last_order_id": "NC-10891",
        "city": "Austin",
    },
}

DEFAULT_PROFILE = {
    "name": "Guest",
    "membership_tier": "Standard",
    "last_order_id": None,
    "city": None,
}


def get_profile(user_id: str) -> dict:
    return MOCK_PROFILES.get(user_id.lower(), {**DEFAULT_PROFILE, "name": user_id})
