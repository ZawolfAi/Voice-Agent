"""Manual integration smoke test. Never commit a provider key in this file."""
import os

from openai import OpenAI

client = OpenAI(
    api_key=os.environ["AI_API_KEY"],
    base_url=os.environ.get("AI_BASE_URL", "https://api.openai.com/v1")
)

response = client.chat.completions.create(
    model="gpt-5.6-sol",
    messages=[
        {
            "role": "user",
            "content": "Hello, tell me who you are."
        }
    ]
)

print(response.choices[0].message.content)
