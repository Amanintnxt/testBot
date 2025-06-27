import os
import time
import openai
import asyncio
from flask import Flask, request
from dotenv import load_dotenv
from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings, TurnContext
from botbuilder.schema import Activity

# Load .env if running locally
load_dotenv()

# Flask app
app = Flask(__name__)

# Environment variables
APP_ID = os.getenv("MicrosoftAppId")
APP_PASSWORD = os.getenv("MicrosoftAppPassword")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
ASSISTANT_ID = os.getenv("ASSISTANT_ID")

# OpenAI Azure setup
openai.api_key = AZURE_OPENAI_API_KEY
openai.api_type = "azure"
openai.api_version = "2024-05-01-preview"
openai.base_url = AZURE_OPENAI_ENDPOINT.rstrip("/") + "/openai/v1"

# Bot Framework Adapter
adapter_settings = BotFrameworkAdapterSettings(APP_ID, APP_PASSWORD)
adapter = BotFrameworkAdapter(adapter_settings)


# Message handler function
async def handle_message(turn_context: TurnContext):
    user_input = turn_context.activity.text

    # Step 1: Create a thread
    thread = openai.beta.threads.create()

    # Step 2: Add user message to thread
    openai.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=user_input
    )

    # Step 3: Run the Assistant on that thread
    run = openai.beta.threads.runs.create(
        assistant_id=ASSISTANT_ID,
        thread_id=thread.id
    )

    # Step 4: Wait for Assistant to complete
    while run.status != "completed":
        time.sleep(1)
        run = openai.beta.threads.runs.retrieve(
            thread_id=thread.id, run_id=run.id)

    # Step 5: Get reply
    messages = openai.beta.threads.messages.list(thread_id=thread.id)
    if messages.data:
        reply = messages.data[0].content[0].text.value
    else:
        reply = "No response from Assistant."

    # Send reply back to user
    await turn_context.send_activity(reply)


# Health check route
@app.route("/", methods=["GET"])
def index():
    return "Azure OpenAI Bot is running."


# Main bot route (used by Azure Bot Service)
@app.route("/api/messages", methods=["POST"])
def messages():
    try:
        activity = Activity().deserialize(request.json)
        auth_header = request.headers.get("Authorization", "")
        return asyncio.run(adapter.process_activity(activity, auth_header, handle_message))
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return f"Error: {e}", 500


# Run locally or on Render
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3978)
