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

# Credentials and keys
APP_ID = os.getenv("MicrosoftAppId", "")
APP_PASSWORD = os.getenv("MicrosoftAppPassword", "")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
ASSISTANT_ID = os.getenv("ASSISTANT_ID")

# Azure OpenAI config
openai.api_type = "azure"
openai.api_version = "2024-05-01-preview"
openai.api_key = AZURE_OPENAI_API_KEY
openai.azure_endpoint = AZURE_OPENAI_ENDPOINT.rstrip("/")

# Flask & Bot setup
app = Flask(__name__)
adapter_settings = BotFrameworkAdapterSettings(APP_ID, APP_PASSWORD)
adapter = BotFrameworkAdapter(adapter_settings)

# Memory per user/session
thread_map = {}


async def handle_message(turn_context: TurnContext):
    user_id = turn_context.activity.from_property.id
    user_input = turn_context.activity.text

    # 🛑 Blank message handler
    if not user_input or not user_input.strip():
        await turn_context.send_activity("Hello! How can I assist you today?")
        return

    try:
        # 👇 Show typing indicator immediately
        await turn_context.send_activity(Activity(type="typing"))

        # Get/create OpenAI thread ID with memory
        thread_id = thread_map.get(user_id)
        if not thread_id:
            thread = openai.beta.threads.create()
            thread_id = thread.id
            thread_map[user_id] = thread_id

        # Add this user message to the assistant's thread
        openai.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=user_input
        )

        # Start Assistant run
        run = openai.beta.threads.runs.create(
            assistant_id=ASSISTANT_ID,
            thread_id=thread_id
        )

        # Poll for run status until done (completed, failed or cancelled)
        while run.status not in ["completed", "failed", "cancelled"]:
            time.sleep(1)
            run = openai.beta.threads.runs.retrieve(
                thread_id=thread_id,
                run_id=run.id
            )

        # Get the latest assistant reply when done
        messages = openai.beta.threads.messages.list(thread_id=thread_id)
        assistant_reply = None
        for message in messages.data:
            if message.role == "assistant":
                assistant_reply = message.content[0].text.value
                break

        if not assistant_reply:
            assistant_reply = "Sorry, I didn't get a reply from the assistant."

    except Exception as e:
        logging.error(f"Error handling message: {e}")
        assistant_reply = "Something went wrong."

    # Send reply
    await turn_context.send_activity(Activity(
        type="message",
        text=assistant_reply,
        recipient=turn_context.activity.from_property,
        from_property=turn_context.activity.recipient,
        conversation=turn_context.activity.conversation,
        channel_id=turn_context.activity.channel_id,
        service_url=turn_context.activity.service_url
    ))


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

# Health check


@app.route("/", methods=["GET"])
def health_check():
    return "Teams Bot is running."


# Launch app
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(host="0.0.0.0", port=3978)
