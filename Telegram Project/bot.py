import os
import re
import json
import asyncio
import logging
from urllib.parse import urlparse

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from playwright.async_api import async_playwright
import google.generativeai as genai

import database

# Load environment variables
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Setup logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configure Gemini
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    logger.warning("GEMINI_API_KEY is not set.")

def is_valid_url(url: str) -> bool:
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

def extract_url(text: str) -> str | None:
    # Basic URL extraction
    urls = re.findall(r'(https?://\S+)', text)
    if urls:
        return urls[0]
    return None

async def scrape_page(url: str) -> str | None:
    """Scrapes the page using Playwright and extracts body innerText."""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            # Wait until there are no more than 2 network connections for at least 500 ms.
            await page.goto(url, wait_until="networkidle", timeout=15000)
            
            # Extract raw innerText from body
            inner_text = await page.evaluate("document.body.innerText")
            await browser.close()
            return inner_text
    except Exception as e:
        logger.error(f"Error scraping {url}: {e}")
        return None

def parse_item_with_gemini(text: str) -> dict | None:
    """Uses Gemini API to extract item name and price."""
    if not GEMINI_API_KEY:
        logger.error("Gemini API key is not configured.")
        return None
        
    try:
        model = genai.GenerativeModel(
            'gemini-1.5-flash',
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema={
                    "type": "OBJECT",
                    "properties": {
                        "item_name": {"type": "STRING"},
                        "price": {"type": "NUMBER"}
                    },
                    "required": ["item_name", "price"]
                }
            )
        )
        
        prompt = f"Extract the primary product name and its price from the following raw webpage text. Return strictly in JSON format with 'item_name' and 'price' keys.\n\nText:\n{text[:10000]}" # Limiting text length just in case
        
        response = model.generate_content(prompt)
        
        if response.text:
            data = json.loads(response.text)
            return data
            
    except Exception as e:
        logger.error(f"Error parsing with Gemini: {e}")
        
    return None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles incoming messages, looking for URLs to process."""
    if not update.message or not update.message.text:
        return
        
    message_text = update.message.text
    url = extract_url(message_text)
    
    if url and is_valid_url(url):
        processing_msg = await update.message.reply_text("Checking that link...")
        
        # 1. Scrape the page
        raw_text = await scrape_page(url)
        if not raw_text:
            await processing_msg.edit_text("Sorry, I couldn't load that page.")
            return
            
        # 2. Parse with Gemini
        item_data = parse_item_with_gemini(raw_text)
        if not item_data or 'item_name' not in item_data or 'price' not in item_data:
            await processing_msg.edit_text("Sorry, I couldn't find an item name and price on that page.")
            return
            
        item_name = item_data['item_name']
        price = float(item_data['price'])
        
        # 3. Save to database
        try:
            database.add_item(item_name, price)
        except Exception as e:
            logger.error(f"Database error: {e}")
            await processing_msg.edit_text("Error saving item to the database.")
            return
            
        # 4. Get total cost and reply
        total_cost = database.get_total_cost()
        
        reply_text = (
            f"✅ **Added to Wishlist!**\n"
            f"**Item:** {item_name}\n"
            f"**Price:** ${price:.2f}\n\n"
            f"💰 **New Total Cost:** ${total_cost:.2f}"
        )
        
        await processing_msg.edit_text(reply_text, parse_mode='Markdown')
        
    else:
        # Not a URL
        await update.message.reply_text("Please send me a link to a product you want to add to your wishlist.")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a greeting when the command /start is issued."""
    await update.message.reply_text("Hi! Send me a link to a product and I'll add it to your wishlist.")


def main() -> None:
    """Start the bot."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set in .env file.")
        return
        
    database.init_db()
    
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(MessageHandler(filters.COMMAND & filters.Regex(r'^/start$'), start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot is starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
