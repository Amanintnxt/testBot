import os
import time
import openai
import asyncio
import logging

from flask import Flask, request, jsonify
from dotenv import load_dotenv
from flask_cors import CORS
from botbuilder.schema import Activity

# Load environment variables
load_dotenv()

# Flask setup
app = Flask(__name__)
CORS(app, resources={r"/api/messages": {"origins": "*"}},
     supports_credentials=True)

# Logging
logging.basicConfig(level=logging.INFO)

# Environment variables
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
ASSISTANT_ID = os.getenv("ASSISTANT_ID")

# OpenAI config
openai.api_type = "azure"
openai.api_version = "2024-05-01-preview"
openai.api_key = AZURE_OPENAI_API_KEY
openai.azure_endpoint = AZURE_OPENAI_ENDPOINT.rstrip("/")

# Async message handler


async def handle_message(user_input: str) -> str:
    try:
        # Create thread
        thread = openai.beta.threads.create()

        # Add user message
        openai.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=user_input
        )

        # Run assistant
        run = openai.beta.threads.runs.create(
            assistant_id=ASSISTANT_ID,
            thread_id=thread.id
        )

        # Wait for completion
        while run.status not in ["completed", "failed", "cancelled"]:
            time.sleep(1)
            run = openai.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id
            )

        # Get reply
        messages = openai.beta.threads.messages.list(thread_id=thread.id)
        if messages.data and messages.data[0].content:
            return messages.data[0].content[0].text.value
        else:
            return "No response from Assistant."

    except Exception as e:
        logging.error(f"❌ Error in handle_message: {e}")
        return f"Error: {str(e)}"

# Health check


@app.route("/", methods=["GET"])
def index():
    return "✅ Azure OpenAI Bot is running."

# Handle preflight OPTIONS (CORS)


@app.route("/api/messages", methods=["OPTIONS"])
def options():
    return '', 200

# Main bot endpoint


@app.route("/api/messages", methods=["POST"])
def messages():
    try:
        logging.info("📩 POST /api/messages")
        if not request.json:
            return jsonify({"error": "Empty request"}), 400

        # Extract Bot Framework message
        try:
            activity = Activity().deserialize(request.json)
            user_input = getattr(activity, "text", "Hello")
        except Exception as e:
            logging.warning(f"⚠️ Fallback parse: {e}")
            user_input = request.json.get("text", "Hello")

        reply = asyncio.run(handle_message(user_input))

        return jsonify({
            "type": "message",
            "text": reply
        })

    except Exception as e:
        logging.error(f"❌ Error in /api/messages: {e}")
        return jsonify({"error": str(e)}), 500


# Run Flask app
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3978)
