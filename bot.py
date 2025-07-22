import os
import time
import openai
import asyncio
import logging
from dotenv import load_dotenv
from flask import Flask, request, Response
from botbuilder.core import BotFrameworkAdapterSettings, BotFrameworkAdapter, TurnContext
from botbuilder.schema import Activity

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

        # Stream OpenAI response
        response = openai.ChatCompletion.create(
            model="gpt-35-turbo",  # or your Azure deployment name
            messages=[{"role": "user", "content": user_input}],
            stream=True,
            api_key=AZURE_OPENAI_API_KEY,
            api_base=AZURE_OPENAI_ENDPOINT,
            api_type="azure",
            api_version="2024-05-01-preview"
        )

        partial = ""
        for chunk in response:
            delta = chunk["choices"][0]["delta"].get("content", "")
            if delta:
                partial += delta
                # Send each partial as a new message (Teams will show as separate bubbles)
                await turn_context.send_activity(Activity(
                    type="message",
                    text=partial,
                    recipient=turn_context.activity.from_property,
                    from_property=turn_context.activity.recipient,
                    conversation=turn_context.activity.conversation,
                    channel_id=turn_context.activity.channel_id,
                    service_url=turn_context.activity.service_url
                ))

    except Exception as e:
        logging.error(f"Error handling message: {e}")
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
