"""Domain errors for pubsub."""


class PubSubError(Exception):
    """Base exception for pubsub errors."""


class TopicNotFoundError(PubSubError):
    """Raised when publishing to or subscribing to an unknown topic."""


class SubscriptionClosedError(PubSubError):
    """Raised when an operation is attempted on a closed Subscription."""


class HandlerError(PubSubError):
    """Raised when a registered handler raises during dispatch.

    Holds the original exception in ``.cause`` so callers can inspect
    the underlying failure.
    """

    def __init__(self, message: str, cause: Exception | None = None):
        super().__init__(message)
        self.message = message
        self.cause = cause
