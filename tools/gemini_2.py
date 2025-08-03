from google import genai
from pydantic import BaseModel
import os
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

# 现在您可以通过 os.environ 获取环境变量
api_key = os.getenv("GEMINI_API_KEY")

# The client gets the API key from the environment variable `GEMINI_API_KEY`.
client = genai.Client()

class Recipe(BaseModel):
    recipe_name: str
    ingredients: list[str]

client = genai.Client()

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="List a few popular cookie recipes, and include the amounts of ingredients.",
    config={
        "response_mime_type": "application/json",
        "response_schema": list[Recipe],
    },
)
# Use the response as a JSON string.
print(response.text)

# Use instantiated objects.
my_recipes: list[Recipe] = response.parsed