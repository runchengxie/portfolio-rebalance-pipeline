import os

from dotenv import load_dotenv
from google import genai

# 加载 .env 文件中的环境变量
load_dotenv()

# 现在您可以通过 os.environ 获取环境变量
api_key = os.getenv("GEMINI_API_KEY")

# The client gets the API key from the environment variable `GEMINI_API_KEY`.
client = genai.Client()

response = client.models.generate_content(
    model="gemini-2.5-flash", contents="Explain how AI works in a few words"
)
print(response.text)
