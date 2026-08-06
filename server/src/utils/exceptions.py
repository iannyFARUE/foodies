"""Custom exception classes for Voyage AI interactions and API authentication."""


class VoyageAuthError(Exception):
    def __init__(self, message: str = "Invalid Voyage AI API key"):
        self.message = message
        super().__init__(self.message)


class VoyageAPIError(Exception):
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class APIKeyError(Exception):
    def __init__(self, message: str = "Missing or invalid API key"):
        self.message = message
        super().__init__(self.message)
