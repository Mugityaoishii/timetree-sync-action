from __future__ import annotations

from client import TimeTreeClient


class LoginError(Exception):
    """Raised when login fails."""


class Auth:
    LOGIN_PATH = "/"

    def __init__(self, client: TimeTreeClient) -> None:
        self.client = client

    def health_check(self) -> bool:
        """
        TimeTreeへ接続できるか確認
        """
        response = self.client.request(
            "GET",
            self.LOGIN_PATH,
        )
        return response.ok
