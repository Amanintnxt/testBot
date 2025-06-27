import os
import time
import openai
import asyncio
from flask import Flask, request
from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings, TurnContext
from botbuilder.schema import Activity
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Load ENV variables
APP_ID = os.getenv("MicrosoftAppId")
APP_PASSWORD = os.getenv("MicrosoftAppPassword")
OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
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

# Message handler


async def handle_message(turn_context: TurnContext):
    user_input = turn_context.activity.text
    try:
        thread = openai.beta.threads.create()
        openai.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=user_input
        )
        run = openai.beta.threads.runs.create(
            assistant_id=ASSISTANT_ID,
            thread_id=thread.id
        )
        while run.status != "completed":
            time.sleep(1)
            run = openai.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id
            )

        messages = openai.beta.threads.messages.list(thread_id=thread.id)
        reply = messages.data[0].content[0].text.value if messages.data else "No reply received."

    except Exception as e:
        reply = f"❌ Error: {str(e)}"
        print("BOT ERROR:", str(e))

    await turn_context.send_activity(reply)

# Home route for quick check


@app.route("/")
def home():
    return "Bot is running!"

# Microsoft Bot Framework message endpoint


@app.route("/api/messages", methods=["POST"])
def messages():
    activity = Activity().deserialize(request.json)

    # For local/dev testing: bypass full auth pipeline
    class NoAuthAdapter(BotFrameworkAdapter):
        async def _authenticate_request(self, activity, auth_header):
            return None  # skip auth completely

    # Use custom adapter (skips JWT check)
    local_adapter = NoAuthAdapter(adapter_settings)

    try:
        return asyncio.run(local_adapter.process_activity(activity, "", handle_message))
    except Exception as e:
        print("❌ Internal error:", str(e))
        return "Internal Server Error", 500


# Run the app
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3978)
