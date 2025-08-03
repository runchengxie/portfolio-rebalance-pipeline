import inspect, pathlib
from google import genai

print("google-genai version:", genai.__version__)
print("located at:", pathlib.Path(genai.__file__).as_posix())

# 实例化一个假客户端（不需要 API Key 也能看签名）
client = genai.Client()          # 若用 Gemini Developer API，可加 api_key='dummy'

sig = inspect.signature(client.models.generate_content)
print("generate_content signature:", sig)