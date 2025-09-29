import pytest
from unittest.mock import AsyncMock
from src import services

# Sample data for testing formatting functions
SAMPLE_SEGMENTS = [
    {"speaker": "A", "text": "Hello, this is the first segment."},
    {"speaker": "B", "text": "And this is the second one."},
    {"speaker": "A", "text": "A final remark from speaker A."},
]

def test_format_results_with_speakers():
    """Tests formatting text with speaker labels."""
    expected_output = (
        "Спикер A:\nHello, this is the first segment.\n\n"
        "Спикер B:\nAnd this is the second one.\n\n"
        "Спикер A:\nA final remark from speaker A."
    )
    assert services.format_results_with_speakers(SAMPLE_SEGMENTS) == expected_output

def test_format_results_plain():
    """Tests formatting text without speaker labels."""
    expected_output = (
        "Hello, this is the first segment.\n\n"
        "And this is the second one.\n\n"
        "A final remark from speaker A."
    )
    assert services.format_results_plain(SAMPLE_SEGMENTS) == expected_output

@pytest.mark.asyncio
async def test_create_yoomoney_payment(mocker):
    """Tests the YooMoney payment link creation."""
    # Mock the httpx.AsyncClient
    mock_async_client = mocker.patch('httpx.AsyncClient', autospec=True)
    
    # We need to mock the async context manager (__aenter__ and __aexit__)
    mock_instance = mock_async_client.return_value
    mock_instance.__aenter__.return_value.post = AsyncMock()

    user_id = 12345
    amount = 100
    description = "Test Subscription"

    payment_url, payment_label = await services.create_yoomoney_payment(user_id, amount, description)

    # Assert the structure of the returned values
    assert payment_url is not None
    assert payment_label is not None
    assert f"sub_{user_id}" in payment_label
    assert f"receiver={services.YOOMONEY_WALLET}" in payment_url
    assert f"sum={amount}" in payment_url
    assert "targets=Test+Subscription" in payment_url

    # Check that the post method was called (for validation)
    mock_instance.__aenter__.return_value.post.assert_called_once()
