"""
Webhook server for YooMoney payment notifications.
This server runs separately from the bot to handle payment confirmations.
"""

import logging
import asyncio
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
import uvicorn

from src.config import settings
from src.services.payment import confirm_payment_and_activate_subscription
from src.database import init_db

logger = logging.getLogger(__name__)

app = FastAPI(title="WiseVoiceAI Payment Webhook")

@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    await init_db()
    logger.info("Webhook server started and database initialized")

@app.post("/yoomoney/webhook")
async def yoomoney_webhook(request: Request):
    """
    Handle YooMoney payment notifications.
    YooMoney sends POST requests with payment data when payments are completed.
    """
    try:
        # Get form data from YooMoney
        form_data = await request.form()

        # Extract payment information
        notification_type = form_data.get("notification_type")
        operation_id = form_data.get("operation_id")
        amount = form_data.get("amount")
        currency = form_data.get("currency")
        datetime = form_data.get("datetime")
        sender = form_data.get("sender")
        codepro = form_data.get("codepro")  # Protection code (true/false)
        label = form_data.get("label")  # Our payment label
        unaccepted = form_data.get("unaccepted")  # Whether payment was accepted

        logger.info(f"YooMoney webhook received: operation_id={operation_id}, amount={amount}, label={label}, unaccepted={unaccepted}")

        # Only process successful payments
        if unaccepted == "true":
            logger.warning(f"Payment {operation_id} was not accepted (unaccepted=true)")
            return PlainTextResponse("Payment not accepted", status_code=200)

        # Skip test payments (codepro=true means protected/test payment)
        if codepro == "true":
            logger.info(f"Skipping test payment: {operation_id}")
            return PlainTextResponse("Test payment skipped", status_code=200)

        # Check if this is our payment (has label)
        if not label:
            logger.warning("Payment without label received")
            return PlainTextResponse("No label", status_code=200)

        # Activate subscription
        success = await confirm_payment_and_activate_subscription(label)

        if success:
            logger.info(f"Subscription activated successfully for payment label: {label}")
            return PlainTextResponse("OK", status_code=200)
        else:
            logger.error(f"Failed to activate subscription for payment label: {label}")
            return PlainTextResponse("Activation failed", status_code=500)

    except Exception as e:
        logger.error(f"Error processing YooMoney webhook: {e}")
        return PlainTextResponse("Error", status_code=500)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}

if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Run server
    uvicorn.run(
        "webhook_server:app",
        host="0.0.0.0",
        port=8001,  # Different port from Prometheus
        reload=False
    )
