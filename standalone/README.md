# AI Callbot - Standalone Version

The standalone version is a local voice assistant that runs from the terminal and uses your microphone for input. It listens to speech, converts it to text with Deepgram, asks OpenRouter for a short product-aware reply, and speaks the answer back with Deepgram text-to-speech.

## What This Module Does

- captures live microphone audio with `PyAudio`
- sends speech to Deepgram for real-time transcription
- uses OpenRouter chat models for AI replies
- queries `Products.csv` through an in-memory SQLite database
- plays AI responses through the system speakers

## Main Files

- `Encode.py` - main application
- `Products.csv` - product database
- `start_audio.mp3` - optional greeting audio
- `requirements.txt` - Python dependencies
- `.env` - local API keys, not committed to GitHub

## Technologies Used

- Python 3.8+
- Deepgram
- OpenRouter
- SQLite
- Pandas
- PyAudio
- Pydub

## Conversation Flow

1. The app starts and loads the product database.
2. A greeting is played or spoken.
3. Your speech is captured from the microphone.
4. Deepgram converts the speech to text.
5. The AI decides whether to answer directly or generate an SQL query.
6. If SQL is needed, the query runs on the local inventory database.
7. The final response is spoken back to you.
8. The app ends when the user clearly says they are done.

## Database Format

The product CSV uses this structure:

```text
Product Name,Category,Brand,Price in Rupees,Stock,Description
```

The CSV is loaded into SQLite at runtime, so the assistant can answer product questions using real data.

## Setup

### 1. Install Requirements

```powershell
cd standalone
pip install -r requirements.txt
```

### 2. Create `.env`

Create a file named `.env` inside the `standalone` folder:

```env
DEEPGRAM_API_KEY=your_deepgram_api_key
OPENROUTER_API_KEY=your_openrouter_api_key
```

### 3. Install FFmpeg

`pydub` needs FFmpeg for audio playback and conversion. Make sure `ffmpeg` is available from the terminal.

### 4. Run the App

```powershell
python Encode.py
```

## What To Expect When Running

- the app loads the CSV into an in-memory database
- the terminal shows the live transcription status
- product-related questions are answered from the inventory
- responses are played aloud automatically

## Example Use

- User: "Do you have rice?"
- App: checks the database and replies with matching product details
- User: "Yes, buy it"
- App: confirms the item and asks about payment or next steps

## Troubleshooting

- If audio does not play, confirm FFmpeg is installed.
- If the app cannot start, check that both API keys are present in `.env`.
- If microphone input is not detected, confirm the microphone is available to Python.

## Notes

- Do not commit `.env` to GitHub.
- Keep `Products.csv` in the same folder as `Encode.py`.
- The current code uses OpenRouter models, not direct Gemini API calls.
