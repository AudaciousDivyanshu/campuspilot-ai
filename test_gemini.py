
import os
from dotenv import load_dotenv
from google import genai

# Load environment variables from .env
load_dotenv()

# Read the API key securely
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError("GEMINI_API_KEY not found. Check your .env file.")

# Create Gemini client
client = genai.Client(api_key=api_key)

# Send a test message
response = client.models.generate_content(
    model="gemini-3.5-flash-lite",
    contents="Hello! Introduce yourself briefly and explain how you can help a college campus assistant."
)

# Display Gemini's response
print("\nGemini Response:")
print(response.text)
