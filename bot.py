import os
import time
import openai
import asyncio
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from botbuilder.schema import Activity

# Load environment variables
load_dotenv()

# Flask app
app = Flask(__name__)

# Environment Variables
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
ASSISTANT_ID = os.getenv("ASSISTANT_ID")

openai.api_key = AZURE_OPENAI_API_KEY
openai.api_type = "azure"
openai.api_version = "2024-05-01-preview"
openai.azure_endpoint = AZURE_OPENAI_ENDPOINT.rstrip("/")

# Message handler function


async def handle_message(user_input: str) -> str:
    try:
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

        # Step 4: Wait for run to complete
        while run.status not in ["completed", "failed", "cancelled"]:
            time.sleep(1)
            run = openai.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id
            )

        # Step 5: Get final message
        messages = openai.beta.threads.messages.list(thread_id=thread.id)
        if messages.data:
            return messages.data[0].content[0].text.value
        else:
            return "No reply from Assistant."

    except Exception as e:
        return f"Error: {str(e)}"

# Health check route


@app.route("/", methods=["GET"])
def index():
    return "Azure OpenAI Assistant Bot is running."

# POST /api/messages for incoming bot messages


@app.route("/api/messages", methods=["POST"])
def messages():
    try:
        activity = Activity().deserialize(request.json)
        user_input = activity.text or "Hello"
        reply = asyncio.run(handle_message(user_input))
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Run locally or on Render
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3978)
