# AI Calling Agent

This repository contains two related AI voice assistant modules:

- `standalone/` for local microphone-based voice interaction
- `phone_agent/` for Twilio-based outbound phone calls through a web interface

Both modules use the same product database format and the same conversation flow:

- speech recognition with Deepgram
- AI response generation through OpenRouter models
- SQLite product lookup from `Products.csv`
- text-to-speech for spoken replies

## Repository Overview

### 1. Standalone Module
Path: `standalone/Encode.py`

This version runs directly on the local machine. It listens through the microphone, transcribes speech in real time, searches the product database when needed, and speaks the reply back to the user.

### 2. Phone Agent Module
Path: `phone_agent/phone_agent_app.py`

This version exposes a Flask web app, starts outbound calls through Twilio, streams live call audio to Deepgram, and sends AI-generated audio responses back to the caller.

## Main Technologies

- Python 3.8+
- Flask
- Twilio
- Deepgram
- OpenRouter
- SQLite
- Pandas
- Pydub
- PyAudio
- WebSocket client libraries

## Project Structure

```text
ai-calling-agent-main/
|-- standalone/
|   |-- Encode.py
|   |-- Products.csv
|   |-- requirements.txt
|   `-- README.md
|-- phone_agent/
|   |-- phone_agent_app.py
|   |-- Products.csv
|   |-- requirements.txt
|   |-- templates/
|   |   `-- index.html
|   `-- README.md
`-- README.md
```

## Prerequisites

- Python 3.8 or higher
- `pip`
- Git
- FFmpeg installed and available on PATH
- API keys for Deepgram and OpenRouter
- For the phone agent: Twilio account credentials and ngrok

## Common Setup

Clone the repository and open it in terminal:

```powershell
git clone https://github.com/Muhammad-Aamir-Iqbal/AI-Project-AI-calling-agent-.git
cd ai-calling-agent-main
```

Create and activate a virtual environment:

```powershell
python -m venv venv
.\venv\Scripts\activate
```

Install dependencies for the module you want to run:

```powershell
cd standalone
pip install -r requirements.txt
```

or

```powershell
cd phone_agent
pip install -r requirements.txt
```

## Environment Variables

Create a local `.env` file inside the module folder you want to run.

### Standalone Module

```env
DEEPGRAM_API_KEY=your_deepgram_api_key
OPENROUTER_API_KEY=your_openrouter_api_key
```

### Phone Agent Module

```env
DEEPGRAM_API_KEY=your_deepgram_api_key
OPENROUTER_API_KEY=your_openrouter_api_key
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_PHONE_NUMBER=your_twilio_phone_number
NGROK_URL=https://your-ngrok-subdomain.ngrok-free.app
```

## Run the Standalone Module

```powershell
cd standalone
python Encode.py
```

What it does:

- loads `Products.csv` into an in-memory SQLite database
- captures microphone input
- sends audio to Deepgram STT
- generates product-aware replies through OpenRouter
- plays spoken responses through Deepgram TTS

## Run the Phone Agent Module

Open two terminals.

### Terminal 1

```powershell
cd phone_agent
python phone_agent_app.py
```

### Terminal 2

```powershell
ngrok http 5000
```

Then update your Twilio Voice webhook to point to:

```text
https://your-ngrok-subdomain.ngrok-free.app/voice
```

Open the local web app in your browser:

```text
http://127.0.0.1:5000
```

What it does:

- shows a simple call-initiating UI
- starts an outbound call with Twilio
- streams live audio to Deepgram
- generates AI responses from OpenRouter
- returns synthesized audio to the caller

## Database Format

Both modules use the same CSV schema:

```text
Product Name,Category,Brand,Price in Rupees,Stock,Description
```

The CSV is loaded into SQLite at runtime and queried during conversation.

## Notes

- `.env` files are intentionally ignored by Git.
- Do not commit API keys to the repository.
- The code compiles successfully with a syntax-only check on the main entry files.

## Support

If you want, I can also make the standalone and phone-agent module READMEs clean and consistent with this top-level README.
