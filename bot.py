import os
import time
import openai
import asyncio
import logging

from flask import Flask, request, jsonify
from dotenv import load_dotenv
from flask_cors import CORS
from botbuilder.schema import Activity

# Load environment variables from .env
load_dotenv()

# Flask app setup
app = Flask(__name__)
CORS(app, origins=["*"])  # Allow all origins for testing

# Environment variables
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
ASSISTANT_ID = os.getenv("ASSISTANT_ID")

# Azure OpenAI setup
openai.api_type = "azure"
openai.api_version = "2024-05-01-preview"
openai.api_key = AZURE_OPENAI_API_KEY
openai.azure_endpoint = AZURE_OPENAI_ENDPOINT.rstrip("/")

# Async handler for messages


async def handle_message(user_input: str) -> str:
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
            return messages.data[0].content[0].text.value
        else:
            return "No reply from Assistant."
    except Exception as e:
        logging.error(f"[❌] Error in handle_message: {e}")
        return f"Error: {str(e)}"

# Health check


@app.route("/", methods=["GET"])
def index():
    return "Azure OpenAI Assistant Bot is running."

# Main /api/messages endpoint


@app.route("/api/messages", methods=["POST"])
def messages():
    try:
        logging.info("Received message request.")
        if not request.json:
            return jsonify({"error": "Empty request"}), 400

        try:
            activity = Activity().deserialize(request.json)
            user_input = getattr(activity, "text", None) or "Hello"
        except Exception as e:
            logging.warning(f"Activity parsing failed: {e}")
            user_input = request.json.get("text", "Hello")

        reply = asyncio.run(handle_message(user_input))

        return jsonify({
            "type": "message",
            "text": reply
        })

    except Exception as e:
        logging.error(f"[❌] Error in /api/messages: {e}")
        return jsonify({"error": str(e)}), 500


# Run locally or on Render
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(host="0.0.0.0", port=3978)
