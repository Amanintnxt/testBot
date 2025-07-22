import os
import time
import openai
import asyncio
import logging
from dotenv import load_dotenv
from flask import Flask, request, Response
from botbuilder.core import BotFrameworkAdapterSettings, BotFrameworkAdapter, TurnContext
from botbuilder.schema import Activity
import traceback

# Load environment variables
load_dotenv()

# Credentials from environment
APP_ID = os.getenv("MicrosoftAppId", "")
APP_PASSWORD = os.getenv("MicrosoftAppPassword", "")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
ASSISTANT_ID = os.getenv("ASSISTANT_ID")

# OpenAI Azure Configuration
openai.api_type = "azure"
openai.api_version = "2024-05-01-preview"
openai.api_key = AZURE_OPENAI_API_KEY
openai.azure_endpoint = AZURE_OPENAI_ENDPOINT.rstrip("/")

# Flask & Bot setup
app = Flask(__name__)
adapter_settings = BotFrameworkAdapterSettings(APP_ID, APP_PASSWORD)
adapter = BotFrameworkAdapter(adapter_settings)

# To persist memory (per user/session, optional DB later)
thread_map = {}

# Main bot logic


async def handle_message(turn_context: TurnContext):
    user_id = turn_context.activity.from_property.id
    user_input = turn_context.activity.text

    # 🧠 Handle blank messages (prevents crash)
    if not user_input or not user_input.strip():
        await turn_context.send_activity("Hello! How can I assist you today?")
        return

    try:
        # Send typing indicator
        await turn_context.send_activity(Activity(type="typing"))

        loop = asyncio.get_event_loop()

        def blocking_stream():
            return openai.ChatCompletion.create(
                model="gpt-35-turbo",
                messages=[{"role": "user", "content": user_input}],
                stream=True
            )

        response_stream = await loop.run_in_executor(None, blocking_stream)

        partial = ""

        for chunk in response_stream:
            delta = chunk.get("choices", [{}])[0].get(
                "delta", {}).get("content", "")
            if delta:
                partial += delta
                # Send partial updates here — consider throttling in real code
                await turn_context.send_activity(delta)

    except Exception as e:
        logging.error(f"Error handling message: {e}")
        logging.error(traceback.format_exc())
        await turn_context.send_activity("Sorry, something went wrong.")
# 🔁 Endpoint to receive message


@app.route("/api/messages", methods=["POST"])
def messages():
    try:
        if "application/json" not in request.headers.get("Content-Type", ""):
            return Response("Unsupported Media Type", status=415)

        activity = Activity().deserialize(request.json)
        auth_header = request.headers.get("Authorization", "")

        async def process():
            return await adapter.process_activity(activity, auth_header, handle_message)

        result = asyncio.run(process())
        return Response(status=200)

    except Exception as e:
        logging.error(f"Exception in /api/messages: {e}")
        return Response("Internal Server Error", status=500)

# 🩺 Health check


@app.route("/", methods=["GET"])
def health_check():
    return "Teams Bot is running."


# 🚀 Launch app
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(host="0.0.0.0", port=3978)
