import os
import time
import openai
import asyncio
from flask import Flask, request
from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings, TurnContext
from botbuilder.schema import Activity
from dotenv import load_dotenv

# Load environment variables from .env (useful for local testing)
load_dotenv()

# Initialize app
app = Flask(__name__)

# Environment variables
APP_ID = os.getenv("MicrosoftAppId")
APP_PASSWORD = os.getenv("MicrosoftAppPassword")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID = os.getenv("ASSISTANT_ID")
# Optional for Azure OpenAI users
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")

# Configure OpenAI for Azure endpoint
openai.api_key = OPENAI_API_KEY
if AZURE_OPENAI_ENDPOINT:
    openai.base_url = AZURE_OPENAI_ENDPOINT.rstrip("/") + "/openai/v1"
    openai.api_type = "azure"
    # Use the correct version for Assistants API
    openai.api_version = "2024-05-01-preview"

# Set up Microsoft Bot Framework adapter
adapter_settings = BotFrameworkAdapterSettings(APP_ID, APP_PASSWORD)
adapter = BotFrameworkAdapter(adapter_settings)

# Handle messages


async def handle_message(turn_context: TurnContext):
    user_input = turn_context.activity.text

    # Create assistant thread and run
    thread = openai.beta.threads.create()
    openai.beta.threads.messages.create(
        thread_id=thread.id, role="user", content=user_input)
    run = openai.beta.threads.runs.create(
        assistant_id=ASSISTANT_ID, thread_id=thread.id)

    # Wait for the run to complete
    while run.status != "completed":
        time.sleep(1)
        run = openai.beta.threads.runs.retrieve(
            thread_id=thread.id, run_id=run.id)

    # Get final message
    messages = openai.beta.threads.messages.list(thread_id=thread.id)
    reply = messages.data[0].content[0].text.value if messages.data else "No reply received."

    await turn_context.send_activity(reply)

# Endpoint for Azure Bot to call


@app.route("/api/messages", methods=["POST"])
def messages():
    activity = Activity().deserialize(request.json)
    auth_header = request.headers.get("Authorization", "")
    return asyncio.run(adapter.process_activity(activity, auth_header, handle_message))


# For local testing
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3978)
