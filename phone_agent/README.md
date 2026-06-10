# AI Voice Calling Bot - Phone Agent Version

This module is the web-based calling version of the project. A user opens the local Flask app, enters a phone number, and the system places an outbound Twilio call. The caller then talks to the AI agent through live audio streaming.

## What This Module Does

- provides a simple browser UI for starting a call
- places an outbound phone call with Twilio
- streams call audio to Deepgram for speech-to-text
- uses OpenRouter for AI conversation
- looks up products from the local SQLite inventory
- sends spoken replies back to the caller using Deepgram TTS

## Main Files

- `phone_agent_app.py` - Flask backend and call logic
- `templates/index.html` - browser UI
- `Products.csv` - product database
- `requirements.txt` - Python dependencies
- `.env` - local API keys and Twilio settings, not committed to GitHub

## Technologies Used

- Python 3.8+
- Flask
- Twilio
- Deepgram
- OpenRouter
- SQLite
- Pandas
- Pydub
- WebSocket streaming
- ngrok for local webhook exposure

## How the Flow Works

1. Open the Flask web app in your browser.
2. Enter a valid phone number.
3. The app starts an outbound Twilio call.
4. Twilio connects the call audio to a websocket stream.
5. Deepgram transcribes the live audio.
6. OpenRouter generates the response.
7. The response is converted to speech and sent back into the call.
8. The conversation continues until the caller ends it.

## Database Format

The same CSV schema is used in this module:

```text
Product Name,Category,Brand,Price in Rupees,Stock,Description
```

The data is loaded into SQLite at startup and used during the conversation for product lookups.

## Setup

### 1. Install Requirements

```powershell
cd phone_agent
pip install -r requirements.txt
```

### 2. Create `.env`

Create a file named `.env` inside the `phone_agent` folder:

```env
DEEPGRAM_API_KEY=your_deepgram_api_key
OPENROUTER_API_KEY=your_openrouter_api_key
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_PHONE_NUMBER=your_twilio_phone_number
NGROK_URL=https://your-ngrok-subdomain.ngrok-free.app
```

### 3. Start ngrok

```powershell
ngrok http 5000
```

Use the ngrok HTTPS URL as your Twilio webhook base.

### 4. Run the App

```powershell
python phone_agent_app.py
```

### 5. Open the Web UI

Open:

```text
http://127.0.0.1:5000
```

## Twilio Webhook Setup

In the Twilio console, set the voice webhook for your number to:

```text
https://your-ngrok-subdomain.ngrok-free.app/voice
```

This lets Twilio forward the call audio to your local Flask app.

## What To Expect When Running

- the browser shows a call button and status text
- the app starts the outbound call when you click the button
- the voice stream is handled in real time
- product questions are answered using the local database
- the call ends when the caller clearly finishes the conversation

## Troubleshooting

- If the call does not start, check Twilio credentials in `.env`.
- If the webhook does not work, confirm ngrok is running and the URL is current.
- If audio does not flow, confirm Deepgram and Twilio credentials are valid.
- If the app fails to start, check that all Python dependencies are installed.

## Notes

- Do not commit `.env` to GitHub.
- Keep `Products.csv` in the same folder as `phone_agent_app.py`.
- The current code uses OpenRouter models for the AI layer.
