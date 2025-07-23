import os
import json
import logging
import requests
import asyncio
from dotenv import load_dotenv
from flask import Flask, request, Response
from botbuilder.core import BotFrameworkAdapterSettings, BotFrameworkAdapter, TurnContext
from botbuilder.schema import Activity

# Load environment variables
load_dotenv()

# Credentials
APP_ID = os.getenv("MicrosoftAppId", "")
APP_PASSWORD = os.getenv("MicrosoftAppPassword", "")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT").rstrip("/")
ASSISTANT_ID = os.getenv("ASSISTANT_ID")
API_VERSION = "2024-05-01-preview"  # Use your deployed API version

# Flask & Bot setup
app = Flask(__name__)
adapter_settings = BotFrameworkAdapterSettings(APP_ID, APP_PASSWORD)
adapter = BotFrameworkAdapter(adapter_settings)

# To keep track of threads per user
thread_map = {}


async def handle_message(turn_context: TurnContext):
    user_id = turn_context.activity.from_property.id
    user_input = turn_context.activity.text

    if not user_input or not user_input.strip():
        await turn_context.send_activity("Hello! How can I assist you today?")
        return

    try:
        # Typing indicator
        await turn_context.send_activity(Activity(type="typing"))

        # Create or get thread_id
        thread_id = thread_map.get(user_id)
        if not thread_id:
            # Create thread via SDK (simpler)
            # Note: `openai.beta.threads.create()` is imported from openai SDK
            import openai
            openai.api_type = "azure"
            openai.api_version = API_VERSION
            openai.api_key = AZURE_OPENAI_API_KEY
            openai.azure_endpoint = AZURE_OPENAI_ENDPOINT

            thread = openai.beta.threads.create()
            thread_id = thread.id
            thread_map[user_id] = thread_id

        # Add user message to thread via SDK
        # This doesn't stream, just stores your message for context
        openai.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=user_input
        )

        # Prepare manual streaming run - raw HTTP POST request
        url = f"{AZURE_OPENAI_ENDPOINT}/openai/assistants/{API_VERSION}/threads/runs"
        headers = {
            "api-key": AZURE_OPENAI_API_KEY,
            "Content-Type": "application/json"
        }
        payload = {
            "assistant_id": ASSISTANT_ID,
            "thread_id": thread_id,
            "stream": True
        }

        # Run the streaming request in a thread safe way for asyncio
        loop = asyncio.get_event_loop()

        def stream_run():
            collected_text = ""
            with requests.post(url, headers=headers, json=payload, stream=True) as r:
                r.raise_for_status()

                for line in r.iter_lines():
                    if line:
                        decoded = line.decode("utf-8")
                        if decoded.startswith("data: "):
                            data_str = decoded[len("data: "):].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                data_json = json.loads(data_str)
                                delta = data_json.get("choices", [{}])[
                                    0].get("delta", {})
                                chunk = delta.get("content", "")
                                collected_text += chunk
                            except json.JSONDecodeError:
                                # Ignore malformed JSON fragments
                                pass
            return collected_text

        collected_reply = await loop.run_in_executor(None, stream_run)

        if not collected_reply:
            collected_reply = "Sorry, I didn't get a reply from the assistant."

    except Exception as e:
        logging.error(f"Error in handle_message: {e}")
        collected_reply = "Something went wrong."

    # Send the full reply to the user
    await turn_context.send_activity(Activity(
        type="message",
        text=collected_reply,
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

        from botbuilder.schema import Activity
        activity = Activity().deserialize(request.json)
        auth_header = request.headers.get("Authorization", "")

        async def process():
            return await adapter.process_activity(activity, auth_header, handle_message)

        asyncio.run(process())
        return Response(status=200)

    except Exception as e:
        logging.error(f"Exception in /api/messages: {e}")
        return Response("Internal Server Error", status=500)


@app.route("/", methods=["GET"])
def health_check():
    return "Teams Bot is running."


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(host="0.0.0.0", port=3978)
