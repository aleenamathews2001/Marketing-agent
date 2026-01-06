class BrevoApiError(Exception):
    """Custom exception for Brevo API errors."""

    def __init__(self, status_code: int, message: str, details: dict | None = None):
        super().__init__(f"[{status_code}] {message}")
        self.status_code = status_code
        self.message = message
        self.details = details or {}
