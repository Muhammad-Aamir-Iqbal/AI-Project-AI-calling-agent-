from flask import Flask, request, Response, render_template
from flask_sock import Sock
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream
from twilio.rest import Client
import os
import json
import base64
import sqlite3
import pandas as pd
import requests
import io
import audioop
import threading
import time
from openai import OpenAI
from pydub import AudioSegment
from dotenv import load_dotenv
import websocket as ws_client

load_dotenv()

app = Flask(__name__)
sock = Sock(app)

# ==================== CONFIG ====================
DEEPGRAM_API_KEY = os.getenv('DEEPGRAM_API_KEY')
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')

# NGROK URL - .env se lo ya manually set karo
NGROK_URL = os.getenv('NGROK_URL', 'https://kangaroo-smugly-providing.ngrok-free.app')

# STRIP https:// for wss://
NGROK_HOST = NGROK_URL.replace('https://', '').replace('http://', '')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PRODUCTS_CSV_PATH = os.path.join(SCRIPT_DIR, 'Products.csv')

# ==================== TWILIO CLIENT ====================
twilio_client = None
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    print(f'[TWILIO] Client initialized')
    print(f'[TWILIO] Using ngrok URL: {NGROK_URL}')
    print(f'[TWILIO] Stream host: {NGROK_HOST}')
else:
    print('[TWILIO] Missing credentials — outbound calls disabled')

# ==================== DATABASE ====================
print('[DB] Loading inventory...')
df = pd.read_csv(PRODUCTS_CSV_PATH)
conn = sqlite3.connect(':memory:', check_same_thread=False)
df.to_sql('inventory', conn, if_exists='replace', index=False)
print(f'[DB] Loaded! {len(df)} products')

# ==================== OPENROUTER AGENT ====================
class FastPhoneAgent:
    def __init__(self, api_key):
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            default_headers={
                "HTTP-Referer": "http://localhost:3000",
                "X-Title": "AI Voice Agent",
            }
        )
        self.models = [
            "meta-llama/llama-3-8b-instruct",
            "meta-llama/llama-3.1-8b-instruct"
        ]
        self.model = self.models[0]
        self.history = []
        self.setup_chat()

    def setup_chat(self):
        system_prompt = """You are Taaniya, a professional sales assistant at KGP Marketplace.

ABSOLUTE RULES — NEVER BREAK THESE:
1. Reply in 1-2 short sentences only.
2. NEVER say "Let me check", "One moment", "I'll see", "Ha ha", laugh, or be casual.
3. If you need data, output ONLY this exact format — no other text before or after:
   SQL: SELECT ... FROM inventory ...
4. When you get SQL results, describe ONLY what was found with exact prices. If nothing found, say "We don't have that" and suggest ONE similar item with price.
5. ALWAYS end with a question to continue conversation.
6. After user confirms a purchase, chooses payment method, or says they paid — NEVER say EXIT. Instead say: "Great! Would you like to buy anything else?"
7. ONLY say EXIT when user clearly says they are done (e.g., "no", "bye", "that's all", "I'm done", "nothing else"). When you say EXIT, it must be at the very end of a friendly goodbye message like "Thank you for shopping at KGP! EXIT"
8. NEVER make up products. Only use data from SQL results.
9. NEVER suggest Electronics unless user specifically asks for electronics.
10. If user asks for categories, list real categories from the database.

CONVERSATION FLOW:
- User asks for product → SQL query → describe with price → ask if they want it
- User says yes/buy/proceed → confirm item → ask quantity if needed → state total → ask "Cash or card?"
- User says payment method → confirm order → ask "Would you like to buy anything else?"
- User says yes → "Awesome! What else would you like?" → continue
- User says no/bye/done → friendly goodbye → add EXIT at the very end

DATABASE: inventory(Product Name, Category, Brand, Price in Rupees, Stock, Description)

EXAMPLES:
User: "What categories do you have?"
SQL: SELECT DISTINCT Category FROM inventory ORDER BY Category LIMIT 10
Reply: "We have Clothing, Electronics, Groceries, Fruits, Vegetables, Medicine, and more. Which category interests you?"

User: "I want rice"
SQL: SELECT * FROM inventory WHERE "Product Name" LIKE '%rice%' LIMIT 5
Reply: "We have Basmati Rice by India Gate for ₹899. Premium aged rice. Shall I add it to your cart?"

User: "Yes buy it"
Reply: "Great choice! Total is ₹899. Would you like to pay by cash or card?"

User: "Cash"
Reply: "Perfect! Your order for Basmati Rice is confirmed at ₹899. Would you like to buy anything else?"

User: "No thanks"
Reply: "Thank you for shopping at KGP Marketplace! Have a great day. EXIT"

OPENING: "Hello! I'm Taaniya from KGP Marketplace, your personal shopping assistant. We have over 150 products across 25 categories. What are you looking for today?""" 
        
        self.history = [{"role": "system", "content": system_prompt}]
        
        for i, model in enumerate(self.models):
            try:
                resp = self.client.chat.completions.create(
                    model=model,
                    messages=self.history,
                    max_tokens=30,
                    temperature=0.3,
                    timeout=8
                )
                self.model = model
                print(f'[AI] Model ready: {model}')
                return
            except Exception as e:
                print(f'[AI] {model} failed: {str(e)[:60]}')
                continue
        
        self.model = self.models[-1]
        print(f'[AI] Fallback model: {self.model}')

    def get_reply(self, message, max_tokens=80):
        try:
            self.history.append({"role": "user", "content": message})
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=self.history,
                max_tokens=max_tokens,
                temperature=0.3,
                timeout=10
            )
            reply = resp.choices[0].message.content
            self.history.append({"role": "assistant", "content": reply})
            return reply.strip()
        except Exception as e:
            print(f"[AI Error]: {e}")
            return "I'm here! What would you like to buy?"

# ==================== DEEPGRAM TTS (Mulaw 8kHz for Twilio) ====================
def get_tts_audio(text):
    try:
        url = "https://api.deepgram.com/v1/speak"
        headers = {
            "Authorization": f"Token {DEEPGRAM_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {"text": text}
        params = {"model": "aura-asteria-en"}
        response = requests.post(url, headers=headers, json=payload, params=params, timeout=10)
        if response.status_code == 200:
            audio = AudioSegment.from_mp3(io.BytesIO(response.content))
            audio = audio.set_frame_rate(8000).set_channels(1).set_sample_width(2)
            raw_data = audio.raw_data
            mulaw_data = audioop.lin2ulaw(raw_data, 2)
            return base64.b64encode(mulaw_data).decode('utf-8')
        else:
            print(f"[TTS Error]: {response.status_code}")
            return None
    except Exception as e:
        print(f"[TTS Exception]: {e}")
        return None

# ==================== WEB PAGE ====================
@app.route('/')
def index():
    return render_template('index.html')

# ==================== OUTBOUND CALL ====================
@app.route('/call', methods=['POST'])
def make_call():
    if not twilio_client:
        return {"error": "Twilio not configured"}, 500
    
    data = request.get_json()
    to_number = data.get('phone')
    
    if not to_number:
        return {"error": "Phone number required"}, 400
    
    try:
        # Use NGROK_URL for webhook
        call = twilio_client.calls.create(
            to=to_number,
            from_=TWILIO_PHONE_NUMBER,
            url=f"{NGROK_URL}/voice"
        )
        print(f'[CALL] Initiated call to {to_number}')
        print(f'[CALL] Webhook URL: {NGROK_URL}/voice')
        return {"success": True, "call_sid": call.sid}
    except Exception as e:
        print(f'[CALL ERROR] {str(e)}')
        return {"error": str(e)}, 500

# ==================== TWILIO VOICE WEBHOOK ====================
@app.route('/voice', methods=['POST'])
def voice():
    response = VoiceResponse()
    connect = Connect()
    
    # CRITICAL FIX: Use wss:// for WebSocket stream
    stream_url = f"wss://{NGROK_HOST}/stream"
    connect.stream(url=stream_url)
    response.append(connect)
    
    print(f'[VOICE] Webhook triggered. Stream URL: {stream_url}')
    
    return Response(str(response), mimetype='text/xml')

# ==================== TWILIO MEDIA STREAM ====================
@sock.route('/stream')
def stream(twilio_ws):
    print('[STREAM] Client connected')
    
    stream_sid = None
    agent = FastPhoneAgent(OPENROUTER_API_KEY)
    stt_ws = None
    stt_connected = False
    current_utterance = []
    processing = False
    pending_buy_more = False
    
    GOODBYE_KEYWORDS = ["bye", "goodbye", "that's all", "i'm done", "nothing else", "no more", "all done"]
    YES_KEYWORDS = ["yes", "yeah", "sure", "yep", "okay", "ok", "ya"]
    NO_KEYWORDS = ["no", "nope", "nah", "not now", "i'm good"]
    
    def send_audio_to_twilio(audio_b64):
        if stream_sid and audio_b64:
            msg = {
                "event": "media",
                "streamSid": stream_sid,
                "media": {"payload": audio_b64}
            }
            try:
                twilio_ws.send(json.dumps(msg))
            except Exception as e:
                print(f'[Twilio Send Error]: {e}')
    
    def process_utterance(utterance):
        nonlocal processing, pending_buy_more
        try:
            utterance_lower = utterance.lower()
            
            # Handle buy more response
            if pending_buy_more:
                if any(k in utterance_lower for k in NO_KEYWORDS + GOODBYE_KEYWORDS):
                    goodbye = "Thank you for shopping at KGP Marketplace! Have a great day. EXIT"
                    audio_b64 = get_tts_audio(goodbye)
                    send_audio_to_twilio(audio_b64)
                    return
                elif any(k in utterance_lower for k in YES_KEYWORDS):
                    pending_buy_more = False
                    response = "Awesome! What else would you like to buy?"
                    audio_b64 = get_tts_audio(response)
                    send_audio_to_twilio(audio_b64)
                    return
                else:
                    pending_buy_more = False
            
            # Normal AI flow
            response = agent.get_reply(utterance, max_tokens=100)
            
            # Handle SQL
            while response.strip().startswith("SQL:"):
                sql_lines = response.strip().split('\n')
                sql_query = sql_lines[0][4:].strip()
                print(f"    🔍 SQL: {sql_query}")
                
                sql_response = ''
                try:
                    result_df = pd.read_sql_query(sql_query, conn)
                    if result_df.empty:
                        sql_response = "SQL Response:\nNO_RESULTS_FOUND"
                    else:
                        rows = []
                        for _, row in result_df.head(5).iterrows():
                            name = row.get('Product Name', 'Unknown')
                            price = row.get('Price in Rupees', 'N/A')
                            brand = row.get('Brand', 'Unknown')
                            rows.append(f"{name} by {brand}: ₹{price}")
                        sql_response = "SQL Response:\n" + "\n".join(rows)
                except Exception as e:
                    sql_response = f"SQL Error: {e}"
                
                response = agent.get_reply(sql_response, max_tokens=120)
            
            clean_response = response.strip()
            
            # Fix inappropriate EXIT
            if 'EXIT' in clean_response:
                if not any(k in utterance_lower for k in GOODBYE_KEYWORDS):
                    clean_response = clean_response.replace('EXIT', '').strip()
                    if "anything else" not in clean_response.lower():
                        clean_response += " Would you like to buy anything else?"
                        pending_buy_more = True
            
            # Auto-add buy more question
            order_signals = ["total comes out", "order is confirmed", "transaction is complete", 
                           "you've paid", "payment received", "order confirmed"]
            if any(sig in clean_response.lower() for sig in order_signals):
                if "anything else" not in clean_response.lower() and 'EXIT' not in clean_response:
                    clean_response += " Would you like to buy anything else?"
                    pending_buy_more = True
            
            print(f"🤖  {clean_response}")
            audio_b64 = get_tts_audio(clean_response)
            send_audio_to_twilio(audio_b64)
            
        finally:
            processing = False
    
    # Deepgram STT (Mulaw 8kHz)
    stt_ws_url = (
        f"wss://api.deepgram.com/v1/listen?"
        f"model=nova-2&language=en-IN&smart_format=true&"
        f"encoding=mulaw&sample_rate=8000&channels=1&"
        f"interim_results=true&utterance_end_ms=1000&endpointing=500"
    )
    headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}
    
    def stt_on_open(ws):
        nonlocal stt_connected
        stt_connected = True
        print('[STT] Connected to Deepgram')
        
    def stt_on_message(ws, message):
        nonlocal current_utterance, processing
        try:
            data = json.loads(message)
            if "channel" in data and "alternatives" in data["channel"]:
                transcript = data["channel"]["alternatives"][0].get("transcript", "")
                is_final = data.get("is_final", False)
                speech_final = data.get("speech_final", False)
                
                if transcript and is_final:
                    current_utterance.append(transcript)
                    
                if speech_final and current_utterance and not processing:
                    processing = True
                    utterance = " ".join(current_utterance)
                    current_utterance = []
                    print(f"\n🎤 Caller said: {utterance}")
                    threading.Thread(target=process_utterance, args=(utterance,), daemon=True).start()
        except Exception as e:
            print(f"[STT Message Error]: {e}")
            
    def stt_on_error(ws, error):
        print(f"[STT Error]: {error}")
        
    def stt_on_close(ws, *args):
        nonlocal stt_connected
        stt_connected = False
        print('[STT] Disconnected')
        
    stt_ws = ws_client.WebSocketApp(
        stt_ws_url,
        header=headers,
        on_open=stt_on_open,
        on_message=stt_on_message,
        on_error=stt_on_error,
        on_close=stt_on_close
    )
    
    stt_thread = threading.Thread(target=stt_ws.run_forever)
    stt_thread.daemon = True
    stt_thread.start()
    
    timeout = 10
    start = time.time()
    while not stt_connected and time.time() - start < timeout:
        time.sleep(0.1)
    
    if not stt_connected:
        print('[FATAL] Deepgram STT connection failed')
        return
    
    # Send opening greeting
    def send_greeting():
        time.sleep(0.8)
        opening = "Hello! I'm Taaniya from KGP Marketplace, your personal shopping assistant. We have over 150 products across 25 categories. What are you looking for today?"
        audio_b64 = get_tts_audio(opening)
        send_audio_to_twilio(audio_b64)
    
    # Main Twilio loop
    try:
        while True:
            message = twilio_ws.receive()
            if message is None:
                break
                
            data = json.loads(message)
            event = data.get('event')
            
            if event == 'connected':
                print('[STREAM] Twilio connected')
                
            elif event == 'start':
                stream_sid = data['start']['streamSid']
                print(f'[STREAM] Call started: {stream_sid}')
                threading.Thread(target=send_greeting, daemon=True).start()
                
            elif event == 'media':
                if stt_ws and stt_connected:
                    payload = base64.b64decode(data['media']['payload'])
                    stt_ws.send(payload, opcode=ws_client.ABNF.OPCODE_BINARY)
                    
            elif event == 'stop':
                print('[STREAM] Call stopped')
                break
                
    except Exception as e:
        print(f'[STREAM Error]: {e}')
    finally:
        if stt_ws:
            stt_ws.close()
        print('[STREAM] Connection closed')

# ==================== RUN ====================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)