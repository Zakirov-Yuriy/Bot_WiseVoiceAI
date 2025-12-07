"""
Webhook server for YooMoney payment notifications.
This server runs separately from the bot to handle payment confirmations.
"""

import logging
import asyncio
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
import uvicorn
from aiogram import Bot

from src.config import settings
from src.services.payment import confirm_payment_and_activate_subscription
from src.database import init_db, get_user_data

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

        # Extract user_id from label (format: sub_{user_id}_{uuid})
        try:
            label_parts = label.split('_')
            if len(label_parts) >= 2:
                user_id = int(label_parts[1])
            else:
                logger.error(f"Invalid label format: {label}")
                return PlainTextResponse("Invalid label", status_code=400)
        except (ValueError, IndexError) as e:
            logger.error(f"Failed to extract user_id from label {label}: {e}")
            return PlainTextResponse("Invalid user_id", status_code=400)

        # Activate subscription
        success = await confirm_payment_and_activate_subscription(label)

        if success:
            logger.info(f"Subscription activated successfully for payment label: {label}")

            # Send notification to user
            try:
                bot = Bot(token=settings.telegram_bot_token)
                await bot.send_message(
                    chat_id=user_id,
                    text="🎉 *Поздравляем!*\n\n✅ Ваша подписка успешно активирована!\n\nТеперь у вас есть неограниченный доступ ко всем функциям бота.",
                    parse_mode='Markdown'
                )
                logger.info(f"Notification sent to user {user_id}")
            except Exception as e:
                logger.error(f"Failed to send notification to user {user_id}: {e}")

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

@app.post("/test/webhook")
async def test_webhook(request: Request):
    """Test endpoint for webhook debugging"""
    try:
        form_data = await request.form()
        logger.info(f"Test webhook received: {dict(form_data)}")
        return PlainTextResponse("Test OK", status_code=200)
    except Exception as e:
        logger.error(f"Test webhook error: {e}")
        return PlainTextResponse("Test Error", status_code=500)

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
