import asyncio
import asyncpg
import os
import logging
from datetime import datetime, timedelta
from telegram import Bot
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))

DB_CONFIG = {
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
    "host": os.getenv("DB_HOST"),
    "port": int(os.getenv("DB_PORT", 5432)),
}

POLL_INTERVAL = 2  
ENV_FILTER = None  

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

logger = logging.getLogger(__name__)


def format_payment(payment: dict) -> str:
    service = payment["service_type"]
    status = payment["status"]

    emoji = "💰"
    if service == "AVIA":
        emoji = "✈️"
    elif service == "ZHD":
        emoji = "🚆"

    status_text = {
        "paid": "✅ PAID",
        "pending": "⏳ PENDING",
        "cancelled": "❌ CANCELLED"
    }.get(status, status.upper())

    return (
        f"{emoji} *Purchase {service}*\n\n"
        f"*ENV:* {payment['environment']}\n"
        f"*Status:* {status_text}\n"
        f"*Payment ID:* `{payment['id']}`\n"
        f"*Partner:* {payment['partner']}\n"
        f"*Amount:* {payment['amount']} {payment['currency']}\n"
        f"*User:* `{payment['user_uuid']}`\n"
        f"*Time:* {payment['created_at']}"
    )


async def create_pool():
    try:
        pool = await asyncpg.create_pool(**DB_CONFIG)
        logger.info("Connected to database")
        return pool
    except Exception as e:
        logger.error(f"DB connection failed: {e}")
        raise


async def fetch_new_payments(pool, last_check):
    query = """
        SELECT * FROM payments
        WHERE created_at > $1
        ORDER BY created_at ASC
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, last_check)
    return [dict(r) for r in rows]


class PaymentMonitor:
    def __init__(self, bot: Bot, pool):
        self.bot = bot
        self.pool = pool
        self.last_check = datetime.utcnow() - timedelta(minutes=1)
        self.sent_ids = set()

    def filter_payment(self, payment):
        if ENV_FILTER and payment["environment"] != ENV_FILTER:
            return False
        if payment["id"] in self.sent_ids:
            return False
        return True

    async def process_payment(self, payment):
        try:
            message = format_payment(payment)
            await self.bot.send_message(
                chat_id=CHAT_ID,
                text=message,
                parse_mode="Markdown"
            )
            self.sent_ids.add(payment["id"])
            logger.info(f"Sent payment {payment['id']}")

            await asyncio.sleep(0.3)

            if len(self.sent_ids) > 10000:
                self.sent_ids.clear()

        except Exception as e:
            logger.error(f"Error sending message: {e}")

    async def run(self):
        while True:
            try:
                logger.info("Polling for new payments...")

                payments = await fetch_new_payments(self.pool, self.last_check)

                if payments:
                    logger.info(f"Found {len(payments)} new payments")

                for payment in payments:
                    if self.filter_payment(payment):
                        await self.process_payment(payment)

                self.last_check = datetime.utcnow()

            except Exception as e:
                logger.error(f"Loop error: {e}")

            await asyncio.sleep(POLL_INTERVAL)


async def main():
    if not BOT_TOKEN or not CHAT_ID:
        raise ValueError("BOT_TOKEN or CHAT_ID not set")

    bot = Bot(token=BOT_TOKEN)
    pool = await create_pool()

    monitor = PaymentMonitor(bot, pool)
    await monitor.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped")