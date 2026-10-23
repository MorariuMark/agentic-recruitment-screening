"""Network failures distinct from invalid or prohibited job URLs."""


class URLResolutionError(ConnectionError):
    """The server could not resolve a URL after bounded DNS retries."""
    retryable = True

    def __init__(self, hostname: str):
        self.hostname = hostname
        super().__init__(
            f"The server could not resolve '{hostname}'. Check the hostname and retry, "
            "or paste the job description text directly.")
