class SalesforceApiError(Exception):
    """Custom exception for Salesforce API errors."""

    def __init__(self, status_code: int, message: str, details: dict | None = None):
        # Format same as Brevo:  [400] Invalid field Name
        super().__init__(f"[{status_code}] {message}")
        self.status_code = status_code
        self.message = message
        self.details = details or {}
