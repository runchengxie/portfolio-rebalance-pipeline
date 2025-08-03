# Gemini API quickstart

This quickstart shows you how to install our [libraries](/gemini-api/docs/libraries) and make your first Gemini API request.

## Before you begin

You need a Gemini API key. If you don't already have one, you can [get it for free in Google AI Studio](https://aistudio.google.com/app/apikey).

## Install the Google GenAI SDK

**Python** (#python) JavaScript (#javascript) Go (#go) Java (#java) Apps Script (#apps-script)

Using [Python 3.9+](https://www.python.org/downloads/), install the [`google-genai` package](https://pypi.org/project/google-genai/) using the following [pip command](https://packaging.python.org/en/latest/tutorials/installing-packages/):

```bash
pip install -q -U google-genai
```

## Make your first request

Here is an example that uses the [`generateContent`](/api/generate-content#method:-models.generatecontent) method to send a request to the Gemini API using the Gemini 2.5 Flash model.

If you [set your API key](/gemini-api/docs/api-key#set-api-env-var) as the environment variable `GEMINI_API_KEY`, it will be picked up automatically by the client when using the [Gemini API libraries](/gemini-api/docs/libraries). Otherwise you will need to [pass your API key](/gemini-api/docs/api-key#provide-api-key-explicitly) as an argument when initializing the client.

Note that all code samples in the Gemini API docs assume that you have set the environment variable `GEMINI_API_KEY`.

**Python** (#python) JavaScript (#javascript) Go (#go) Java (#java) Apps Script (#apps-script) REST (#rest)

```python
from google import genai

# The client gets the API key from the environment variable `GEMINI_API_KEY`
client = genai.Client()

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Explain how AI works in a few words"
)
print(response.text)
```

## "Thinking" is on by default on many of our code samples

Many code samples on this site use the [Gemini 2.5 Flash](/gemini-api/docs/models#gemini-2.5-flash) model, which has the ["thinking"](/gemini-api/docs/thinking) feature enabled by default to enhance response quality. You should be aware that this may increase response time and token usage. If you prioritize speed or wish to minimize costs, you can disable this feature by setting the thinking budget to zero, as shown in the examples below. For more details, see the [thinking guide](/gemini-api/docs/thinking#set-budget).

> **Note:** Thinking is only available on Gemini 2.5 series models and can't be disabled on Gemini 2.5 Pro.

**Python** (#python) JavaScript (#javascript) Go (#go) REST (#rest) Apps Script (#apps-script)

```python
from google import genai
from google.genai import types

client = genai.Client()

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Explain how AI works in a few words",
    config=types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_budget=0) # Disable thinking
    ),
)
print(response.text)
```
