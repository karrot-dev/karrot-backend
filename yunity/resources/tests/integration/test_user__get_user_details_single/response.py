from .initial_data import user

response = {
    "http_status": 200,
    "response": {
        "users": [
            {"display_name": user.display_name, "id": user.id},
        ]
    }
}
