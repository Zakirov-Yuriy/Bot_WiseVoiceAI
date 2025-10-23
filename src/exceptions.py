class BotError(Exception):
    """Base exception for bot-related errors."""
    pass

class PaymentError(BotError):
    """Exception for payment processing errors."""
    pass

class TranscriptionError(BotError):
    """Exception for transcription service errors."""
    pass

class FileProcessingError(BotError):
    """Exception for file processing errors."""
    pass

class APIError(BotError):
    """Exception for external API errors."""
    pass

class NetworkError(APIError):
    """Exception for network-related API errors."""
    pass

class RateLimitError(APIError):
    """Exception for rate limiting errors."""
    pass
