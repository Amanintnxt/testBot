import os
import time
import openai
import asyncio
from flask import Flask, request
from dotenv import load_dotenv
from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings, TurnContext
from botbuilder.schema import Activity

# Load .env variables for local testing
load_dotenv()

# Flask app
app = Flask(__name__)

# Environment variables
APP_ID = os.getenv("MicrosoftAppId")
APP_PASSWORD = os.getenv("MicrosoftAppPassword")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
ASSISTANT_ID = os.getenv("ASSISTANT_ID")

# Setup OpenAI for Azure
openai.api_key = AZURE_OPENAI_API_KEY
openai.api_type = "azure"
openai.api_version = "2024-05-01-preview"
openai.base_url = AZURE_OPENAI_ENDPOINT.rstrip("/") + "/openai/v1"

# Bot Framework Adapter (used even if we bypass auth)
adapter_settings = BotFrameworkAdapterSettings(APP_ID, APP_PASSWORD)
adapter = BotFrameworkAdapter(adapter_settings)

# ---- Message handler function ----


async def handle_message(turn_context: TurnContext):
    user_input = turn_context.activity.text

    # Create Assistant thread
    thread = openai.beta.threads.create()

    # Add message to thread
    openai.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=user_input
    )

    # Run Assistant
    run = openai.beta.threads.runs.create(
        assistant_id=ASSISTANT_ID,
        thread_id=thread.id
    )

    # Wait until run completes
    while run.status != "completed":
        time.sleep(1)
        run = openai.beta.threads.runs.retrieve(
            thread_id=thread.id, run_id=run.id
        )

    # Fetch messages
    messages = openai.beta.threads.messages.list(thread_id=thread.id)
    if messages.data:
        reply = messages.data[0].content[0].text.value
    else:
        reply = "No response from Assistant."

    await turn_context.send_activity(reply)

# ---- Health check route ----


@app.route("/", methods=["GET"])
def home():
    return "Bot is running!"

# ---- Main Bot route (auth bypassed) ----


@app.route("/api/messages", methods=["POST"])
def messages():
    return "OK", 200


# ---- Run locally ----
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3978)
