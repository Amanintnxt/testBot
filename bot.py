import os
import time
import openai
import asyncio
from flask import Flask, request
from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings, TurnContext
from botbuilder.schema import Activity
from dotenv import load_dotenv

# Load environment variables from .env (used for local dev or Render ENV panel)
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Load ENV variables
APP_ID = os.getenv("MicrosoftAppId")
APP_PASSWORD = os.getenv("MicrosoftAppPassword")
OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")  # use AZURE env key name
ASSISTANT_ID = os.getenv("ASSISTANT_ID")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")

# Set OpenAI (Azure) config
openai.api_key = OPENAI_API_KEY
if AZURE_OPENAI_ENDPOINT:
    openai.base_url = AZURE_OPENAI_ENDPOINT.rstrip("/") + "/openai"
    openai.api_type = "azure"
    openai.api_version = "2024-05-01-preview"

# Configure Bot Framework adapter
adapter_settings = BotFrameworkAdapterSettings(APP_ID, APP_PASSWORD)
adapter = BotFrameworkAdapter(adapter_settings)

# Async function to handle incoming messages
async def handle_message(turn_context: TurnContext):
    user_input = turn_context.activity.text

    try:
        # Create a thread
        thread = openai.beta.threads.create()

        # Add user message
        openai.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=user_input
        )

        # Run the assistant
        run = openai.beta.threads.runs.create(
            assistant_id=ASSISTANT_ID,
            thread_id=thread.id
        )

        # Wait for completion
        while run.status != "completed":
            time.sleep(1)
            run = openai.beta.threads.runs.retrieve(
                thread_id=thread.id, run_id=run.id)

        # Get response
        messages = openai.beta.threads.messages.list(thread_id=thread.id)
        reply = messages.data[0].content[0].text.value if messages.data else "No reply received."

    except Exception as e:
        reply = f"Error: {str(e)}"

    await turn_context.send_activity(reply)

# Home route (test with browser)
@app.route("/")
def home():
    return "Bot is running!"

# Microsoft Bot Framework endpoint
@app.route("/api/messages", methods=["POST"])
def messages():
    activity = Activity().deserialize(request.json)
    auth_header = request.headers.get("Authorization", "")
    return asyncio.run(adapter.process_activity(activity, auth_header, handle_message))

# Run the app
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3978)
