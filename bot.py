import os
import time
import openai
import asyncio
import logging
from dotenv import load_dotenv
from flask import Flask, request, Response
from botbuilder.core import BotFrameworkAdapterSettings, BotFrameworkAdapter, TurnContext
from botbuilder.schema import Activity

load_dotenv()

# Bot credentials
APP_ID = os.getenv("MicrosoftAppId", "")
APP_PASSWORD = os.getenv("MicrosoftAppPassword", "")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
ASSISTANT_ID = os.getenv("ASSISTANT_ID")

# Azure OpenAI setup
openai.api_type = "azure"
openai.api_version = "2024-05-01-preview"
openai.api_key = AZURE_OPENAI_API_KEY
openai.azure_endpoint = AZURE_OPENAI_ENDPOINT.rstrip("/")

# Flask app and Bot Adapter setup
app = Flask(__name__)
adapter_settings = BotFrameworkAdapterSettings(APP_ID, APP_PASSWORD)
adapter = BotFrameworkAdapter(adapter_settings)

# Handle messages


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
            reply = "I didn't get a response from Assistant."

    except Exception as e:
        logging.error(f"Error handling message: {e}")
        reply = "Sorry, something went wrong."

    await turn_context.send_activity(Activity(
        type="message",
        text=reply
    ))

# Flask route


@app.route("/api/messages", methods=["POST"])
def messages():
    if "application/json" in request.headers["Content-Type"]:
        body = request.json
    else:
        return Response(status=415)

    activity = Activity().deserialize(body)
    auth_header = request.headers.get("Authorization", "")

    async def aux():
        await adapter.process_activity(activity, auth_header, handle_message)
        return Response(status=200)

    return asyncio.run(aux())

# Health check


@app.route("/", methods=["GET"])
def health():
    return "Bot is running."


# Run app
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(host="0.0.0.0", port=3978)
