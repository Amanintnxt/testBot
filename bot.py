import os
import time
import openai
import asyncio
import logging

from flask import Flask, request
from dotenv import load_dotenv
from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings, TurnContext
from botbuilder.schema import Activity

# Load env variables
load_dotenv()

# Flask app
app = Flask(__name__)

# Azure Credentials
APP_ID = os.getenv("MicrosoftAppId")
APP_PASSWORD = os.getenv("MicrosoftAppPassword")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
ASSISTANT_ID = os.getenv("ASSISTANT_ID")

# Configure OpenAI
openai.api_type = "azure"
openai.api_version = "2024-05-01-preview"
openai.api_key = AZURE_OPENAI_API_KEY
openai.azure_endpoint = AZURE_OPENAI_ENDPOINT.rstrip("/")

# Bot Adapter
adapter_settings = BotFrameworkAdapterSettings(APP_ID, APP_PASSWORD)
adapter = BotFrameworkAdapter(adapter_settings)

# Async function to handle user messages


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

        while run.status not in ["completed", "failed", "cancelled"]:
            time.sleep(1)
            run = openai.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id
            )

        messages = openai.beta.threads.messages.list(thread_id=thread.id)
        if messages.data:
            reply = messages.data[0].content[0].text.value
        else:
            reply = "No reply from Assistant."

        await turn_context.send_activity(reply)

    except Exception as e:
        logging.error(f"[❌] OpenAI error: {e}")
        await turn_context.send_activity("Oops! Something went wrong.")

# Main endpoint for Azure Bot Framework


@app.route("/api/messages", methods=["POST"])
def messages():
    activity = Activity().deserialize(request.json)
    auth_header = request.headers.get("Authorization", "")
    return asyncio.run(adapter.process_activity(activity, auth_header, handle_message))


# Run
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(host="0.0.0.0", port=3978)
