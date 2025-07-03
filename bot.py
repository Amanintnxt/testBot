import os
import time
import openai
import asyncio
import logging
from dotenv import load_dotenv
from flask import Flask, request, Response
from botbuilder.core import BotFrameworkAdapterSettings, BotFrameworkAdapter, TurnContext
from botbuilder.schema import Activity

# Load .env variables
load_dotenv()

# ENV VARIABLES
APP_ID = os.getenv("MicrosoftAppId", "")
APP_PASSWORD = os.getenv("MicrosoftAppPassword", "")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
ASSISTANT_ID = os.getenv("ASSISTANT_ID")

# OpenAI Azure setup
openai.api_key = AZURE_OPENAI_API_KEY
openai.api_type = "azure"
openai.api_version = "2024-05-01-preview"
openai.azure_endpoint = AZURE_OPENAI_ENDPOINT.rstrip("/")

# Flask app setup
app = Flask(__name__)
adapter_settings = BotFrameworkAdapterSettings(APP_ID, APP_PASSWORD)
adapter = BotFrameworkAdapter(adapter_settings)

# Handle incoming messages


async def handle_message(turn_context: TurnContext):
    try:
        user_input = turn_context.activity.text
        print(f"[📩] Received: {user_input}")

        # 1. Create thread
        thread = openai.beta.threads.create()

        # 2. Add message
        openai.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=user_input
        )

        # 3. Run assistant
        run = openai.beta.threads.runs.create(
            assistant_id=ASSISTANT_ID,
            thread_id=thread.id
        )

        # 4. Wait until assistant completes
        while run.status not in ["completed", "failed", "cancelled"]:
            time.sleep(1)
            run = openai.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id
            )

        # 5. Get final message
        messages = openai.beta.threads.messages.list(thread_id=thread.id)
        if messages.data:
            reply = messages.data[0].content[0].text.value
        else:
            reply = "No reply from Assistant."

        print(f"[🤖] Replying: {reply}")

        # 6. Send reply back with correct addressing
        await turn_context.send_activity(Activity(
            type="message",
            text=reply,
            recipient=turn_context.activity.from_property,
            from_property=turn_context.activity.recipient,
            conversation=turn_context.activity.conversation,
            channel_id=turn_context.activity.channel_id,
            service_url=turn_context.activity.service_url
        ))
    except Exception as e:
        logging.error(f"[❌] Error in handle_message: {e}")
        await turn_context.send_activity("Sorry, something went wrong.")

# Route to handle bot messages


@app.route("/api/messages", methods=["POST"])
def messages():
    if request.headers.get("Content-Type", "").startswith("application/json"):
        body = request.get_json(force=True)
    else:
        return Response("Unsupported Media Type", status=415)

    activity = Activity().deserialize(body)
    auth_header = request.headers.get("Authorization", "")
    task = adapter.process_activity(activity, auth_header, handle_message)
    return asyncio.run(task)

# Health check route


@app.route("/", methods=["GET"])
def index():
    return "✅ Azure OpenAI Assistant Bot is running."


# Start Flask app
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(host="0.0.0.0", port=3978)
