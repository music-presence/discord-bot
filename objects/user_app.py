from dataclasses import dataclass


@dataclass
class UserApp:
    app_id: int
    user_id: int
    timestamp: int
