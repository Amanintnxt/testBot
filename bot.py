import os
import time
import openai
import asyncio
import logging
import re
from dotenv import load_dotenv
from flask import Flask, request, Response
from botbuilder.core import BotFrameworkAdapterSettings, BotFrameworkAdapter, TurnContext
from botbuilder.schema import Activity

# Load environment variables
load_dotenv()

# Credentials and keys
APP_ID = os.getenv("MicrosoftAppId", "")
APP_PASSWORD = os.getenv("MicrosoftAppPassword", "")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
ASSISTANT_ID = os.getenv("ASSISTANT_ID")

# Configure OpenAI Azure API
openai.api_type = "azure"
openai.api_version = "2024-05-01-preview"
openai.api_key = AZURE_OPENAI_API_KEY
openai.azure_endpoint = AZURE_OPENAI_ENDPOINT.rstrip("/")

# Flask & Bot setup
app = Flask(__name__)
adapter_settings = BotFrameworkAdapterSettings(APP_ID, APP_PASSWORD)
adapter = BotFrameworkAdapter(adapter_settings)

# Simple memory store for user threads
thread_map = {}

# --- Helper Classes for Query Processing and Response Validation --- #


class QueryProcessor:
    """Classifies the user query and extracts entities/requirements."""

    def __init__(self):
        # Patterns for classification
        self.patterns = {
            'technical_spec': [
                r'\b(specification|spec|range|zoom|resolution|accuracy|output|interface)\b',
                r'\b\d+(\.\d+)?\s*(m|mm|cm|x|times|°c|°f|v|a)\b',
                r'\b(flir|thermal|camera|sensor|transmitter|receiver)\b'
            ],
            'product_recommendation': [
                r'\b(recommend|suggest|best|ideal|which|what)\b.*\b(for|to)\b',
                r'\b(need|want|require|looking for)\b',
                r'\b(application|use case|purpose)\b'
            ],
            'compatibility': [
                r'\b(compatible|work with|connect|interface)\b',
                r'\b(pnp|npn|analog|digital|output)\b'
            ],
            'troubleshooting': [
                r'\b(problem|issue|error|not working|failed|trouble)\b',
                r'\b(fix|repair|solve|debug)\b'
            ],
            'comparison': [
                r'\b(compare|difference|vs|versus|better)\b',
                r'\b(between|among)\b'
            ]
        }

    def classify_query(self, query: str) -> dict:
        query_lower = query.lower()
        scores = {}
        for key, pats in self.patterns.items():
            count = sum(1 for pat in pats if re.search(pat, query_lower))
            scores[key] = count / len(pats)
        primary_type = max(scores, key=scores.get)
        confidence = scores[primary_type]
        entities = self.extract_entities(query_lower)
        return {
            'primary_type': primary_type,
            'confidence': confidence,
            'entities': entities,
            'original_query': query
        }

    def extract_entities(self, query: str) -> dict:
        entities = {
            'product_series': [],
            'ranges': [],
            'features': [],
            'applications': []
        }
        # Detect product series with simple regex (expand as needed)
        product_series_patterns = {
            'FLIR_Ex': r'\bflir\s+ex\b',
            'FLIR_Exx': r'\bflir\s+e\d{2}\b',
            'FLIR_T8xx': r'\bflir\s+t8\d{2}\b',
            'SMT': r'\bsmt\s*\d+\w*\b',
            'ESF': r'\besf\b',
            'ESP': r'\besp\b',
            'BKS': r'\bbks\+?\b',
        }
        for name, pattern in product_series_patterns.items():
            if re.search(pattern, query):
                entities['product_series'].append(name)

        # Ranges (e.g., "5m to 7m")
        ranges = re.findall(
            r'(\d+(?:\.\d+)?)\s*(?:to|-)\s*(\d+(?:\.\d+)?)\s*m', query)
        entities['ranges'].extend(ranges)

        # Features keywords found
        features = ['zoom', 'resolution', 'accuracy', 'output', 'interface']
        for f in features:
            if f in query:
                entities['features'].append(f)

        # Application keywords (expandable)
        applications = ['loop break detection',
                        'temperature monitoring', 'presence detection']
        for app in applications:
            if app in query:
                entities['applications'].append(app)

        return entities


class ResponseValidator:
    """
    Validates the assistant response for coverage and precision, but is now less strict.
    Blocks responses only if they are entirely vague (no numbers, no product, no spec) or say 'I don't know'.
    """

    def __init__(self):
        self.block_threshold = 2  # Only block if multiple vague indicators found

    def validate(self, query_info: dict, response: str) -> dict:
        issues = []
        response_lower = response.lower()
        vague_hits = 0

        # Block if response lacks numbers and no product terms
        if (
            all(x not in response_lower for x in [
                "meter", "m", "range", "flir", "transmitter", "model", "series"])
            and not any(char.isdigit() for char in response_lower)
        ):
            vague_hits += 1
            issues.append(
                "Response does not include any numerical or product-specific info.")

        # Block if assistant clearly says it doesn't know
        if any(phrase in response_lower for phrase in ["i don't know", "not sure", "sorry, i can't", "cannot answer"]):
            vague_hits += 1
            issues.append(
                "Assistant admitted it doesn't know the answer or cannot answer.")

        approved = vague_hits < self.block_threshold
        return {'approved': approved, 'issues': issues}


query_processor = QueryProcessor()
response_validator = ResponseValidator()


async def handle_message(turn_context: TurnContext):
    user_id = turn_context.activity.from_property.id
    user_input = turn_context.activity.text

    if not user_input or not user_input.strip():
        await turn_context.send_activity("Hello! How can I assist you today?")
        return

    try:
        # Show typing indicator immediately
        await turn_context.send_activity(Activity(type="typing"))

        # Get or create thread ID for user
        thread_id = thread_map.get(user_id)
        if not thread_id:
            thread = openai.beta.threads.create()
            thread_id = thread.id
            thread_map[user_id] = thread_id

        # Analyze user query
        query_info = query_processor.classify_query(user_input)

        # Compose enhanced query adding instructions for precision to assistant
        enhancement = "Provide ONLY precise, document-based answers matching ALL user requirements exactly. No vague language or assumptions."
        if query_info['entities'].get('product_series'):
            enhancement += f" Focus on these product series: {', '.join(query_info['entities']['product_series'])}."
        if query_info['entities'].get('ranges'):
            ranges_str = ", ".join([f"{start}m to {end}m" for (
                start, end) in query_info['entities']['ranges']])
            enhancement += f" Ensure products cover the complete sensing range: {ranges_str}."

        enhanced_query = f"{enhancement}\nUser question:\n{user_input}"

        # Add user message to thread
        openai.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=enhanced_query
        )

        # Start new assistant run
        run = openai.beta.threads.runs.create(
            assistant_id=ASSISTANT_ID,
            thread_id=thread_id
        )

        # Poll until run completes/fails/cancelled
        while run.status not in ["completed", "failed", "cancelled"]:
            time.sleep(1)
            run = openai.beta.threads.runs.retrieve(
                thread_id=thread_id,
                run_id=run.id
            )

        # Retrieve latest assistant reply
        messages = openai.beta.threads.messages.list(thread_id=thread_id)
        assistant_reply = None
        for message in reversed(messages.data):
            if message.role == "assistant" and message.content:
                assistant_reply = message.content[0].text.value
                break

        if not assistant_reply:
            assistant_reply = "Sorry, I didn't get a response from the assistant."

        # Validate assistant response
        validation = response_validator.validate(query_info, assistant_reply)

        if not validation['approved']:
            issues_text = " ".join(validation['issues'])
            clarification = f"I want to provide an accurate answer, but noticed some issues: {issues_text} Could you please clarify or rephrase your requirements?"
            assistant_reply = clarification

    except Exception as e:
        logging.error(f"Error handling message: {e}")
        assistant_reply = "Something went wrong while processing your message."

    # Send the reply
    await turn_context.send_activity(Activity(
        type="message",
        text=assistant_reply,
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
