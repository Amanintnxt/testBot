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

# Bot credentials & assistant setup
APP_ID = os.getenv("MicrosoftAppId", "")
APP_PASSWORD = os.getenv("MicrosoftAppPassword", "")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
ASSISTANT_ID = os.getenv("ASSISTANT_ID")

openai.api_type = "azure"
openai.api_version = "2024-05-01-preview"
openai.api_key = AZURE_OPENAI_API_KEY
openai.azure_endpoint = AZURE_OPENAI_ENDPOINT.rstrip("/")

# Flask setup
app = Flask(__name__)
adapter_settings = BotFrameworkAdapterSettings(APP_ID, APP_PASSWORD)
adapter = BotFrameworkAdapter(adapter_settings)

# 🧠 Store for thread IDs
user_threads = {}

# Handler


async def handle_message(turn_context: TurnContext):
    user_input = turn_context.activity.text
    if not user_input.strip():
        await turn_context.send_activity("Hello! How can I assist you today?")
        return

    try:
        conversation_id = turn_context.activity.conversation.id

        # ✅ Reuse thread ID
        if conversation_id not in user_threads:
            thread = openai.beta.threads.create()
            user_threads[conversation_id] = thread.id

        thread_id = user_threads[conversation_id]

        # Add user message
        openai.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=user_input
        )

        # Run assistant
        run = openai.beta.threads.runs.create(
            assistant_id=ASSISTANT_ID,
            thread_id=thread_id
        )

        # Poll until done
        while run.status not in ["completed", "failed", "cancelled"]:
            time.sleep(1)
            run = openai.beta.threads.runs.retrieve(
                thread_id=thread_id,
                run_id=run.id
            )

        # Get response
        messages = openai.beta.threads.messages.list(thread_id=thread_id)
        reply = messages.data[0].content[0].text.value if messages.data else "No response from Assistant."

    except Exception as e:
        logging.error(f"Error: {e}")
        reply = "Sorry, something went wrong."

    await turn_context.send_activity(Activity(
        type="message",
        text=reply,
        recipient=turn_context.activity.from_property,
        from_property=turn_context.activity.recipient,
        conversation=turn_context.activity.conversation,
        channel_id=turn_context.activity.channel_id,
        service_url=turn_context.activity.service_url
    ))

# Flask endpoint


@app.route("/api/messages", methods=["POST"])
def messages():
    if "application/json" not in request.headers.get("Content-Type", ""):
        return Response("Unsupported Media Type", status=415)

    activity = Activity().deserialize(request.json)
    auth_header = request.headers.get("Authorization", "")

    async def process():
        return await adapter.process_activity(activity, auth_header, handle_message)

    result = asyncio.run(process())
    return Response(status=200)

# Health check


@app.route("/", methods=["GET"])
def health_check():
    return "Bot is running."


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(host="0.0.0.0", port=3978)
