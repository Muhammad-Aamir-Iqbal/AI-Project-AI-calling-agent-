from dotenv import load_dotenv
from pathlib import Path
import pyaudio
import os
import json
import threading
import queue
import websocket
import requests
from openai import OpenAI
from pydub import AudioSegment
from pydub.playback import play
import sqlite3
import pandas as pd
import time
import io
import random

# ==================== SETUP ====================
load_dotenv()

SCRIPT_DIR = Path(__file__).parent.resolve()
START_AUDIO_PATH = SCRIPT_DIR / "start_audio.mp3"
PRODUCTS_CSV_PATH = SCRIPT_DIR / "Products.csv"

DEEPGRAM_API_KEY = os.getenv('DEEPGRAM_API_KEY')
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')

if not DEEPGRAM_API_KEY:
    raise ValueError("DEEPGRAM_API_KEY missing!")
if not OPENROUTER_API_KEY:
    raise ValueError("OPENROUTER_API_KEY missing!")

print("[STEP 1] Environment loaded.")

# ==================== TTS CACHE + MEMORY STREAMING ====================
tts_cache = {}

def get_tts_audio(text):
    if text in tts_cache:
        return tts_cache[text]
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
            tts_cache[text] = audio
            return audio
        else:
            print(f"[TTS Error]: {response.status_code}")
            return None
    except Exception as e:
        print(f"[TTS Exception]: {e}")
        return None

# ==================== TTS WORKER ====================
tts_queue = queue.Queue()

def tts_worker():
    while True:
        text = tts_queue.get()
        if text is None:
            break
        try:
            audio = get_tts_audio(text)
            if audio:
                play(audio)
        except Exception as e:
            print(f"[TTS Play Error]: {e}")
        finally:
            tts_queue.task_done()

tts_thread = threading.Thread(target=tts_worker, daemon=True)
tts_thread.start()

def speak(text):
    if text and len(text.strip()) > 0:
        tts_queue.put(text.strip())

# ==================== QUESTION ROTATION ====================
QUESTIONS = [
    "Want it?",
    "Shall I add it to your cart?",
    "Interested?",
    "Want to grab it?",
    "Should I reserve it for you?",
    "Like it?",
]

def get_question():
    return random.choice(QUESTIONS)

# ==================== OPENROUTER AGENT ====================
class FastPhoneAgent:
    def __init__(self, api_key):
        print("[STEP 2] Initializing OpenRouter...")
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
        print("[STEP 3] Loading agent personality...")
        
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

User: "I want iPhone"
SQL: SELECT * FROM inventory WHERE "Product Name" LIKE '%iPhone%'
Reply: "We don't have iPhone, but our Samsung Smartphone has 5G and 128GB for ₹29,999. Want to know more?"

User: "Yes buy it"
Reply: "Great choice! Total is ₹29,999. Would you like to pay by cash or card?"

User: "Cash"
Reply: "Perfect! Your order for Samsung Smartphone is confirmed at ₹29,999. Would you like to buy anything else?"

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
                print(f"[STEP 3] Agent ready! Model: {model}")
                return
            except Exception as e:
                print(f"  ⚠️  {model} failed: {str(e)[:60]}")
                continue
        
        self.model = self.models[-1]
        print(f"[STEP 3] Agent ready with fallback: {self.model}")

    def get_reply(self, message, max_tokens=80):
        try:
            self.history.append({"role": "user", "content": message})
            
            start_time = time.time()
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=self.history,
                max_tokens=max_tokens,
                temperature=0.3,
                timeout=10
            )
            elapsed = time.time() - start_time
            
            reply = resp.choices[0].message.content
            self.history.append({"role": "assistant", "content": reply})
            
            tokens = resp.usage.completion_tokens if hasattr(resp, 'usage') and resp.usage else '?'
            print(f"    ⚡ AI: {elapsed:.2f}s | Model: {self.model.split('/')[-1]} | Tokens: {tokens}")
            
            return reply.strip()
            
        except Exception as e:
            print(f"[AI Error]: {e}")
            return "I'm here! What would you like to buy?"

# ==================== DEEPGRAM STT ====================
class DeepgramSTT:
    def __init__(self, api_key, on_transcript):
        self.api_key = api_key
        self.on_transcript = on_transcript
        self.ws = None
        self.connected = False
        
    def connect(self):
        ws_url = (
            f"wss://api.deepgram.com/v1/listen?"
            f"model=nova-2&language=en-IN&smart_format=true&"
            f"encoding=linear16&sample_rate=16000&channels=1&"
            f"interim_results=true&utterance_end_ms=1000&endpointing=500"
        )
        headers = {"Authorization": f"Token {self.api_key}"}
        
        self.ws = websocket.WebSocketApp(
            ws_url,
            header=headers,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close
        )
        
        self.ws_thread = threading.Thread(target=self.ws.run_forever)
        self.ws_thread.daemon = True
        self.ws_thread.start()
        
        timeout = 10
        start = time.time()
        while not self.connected and time.time() - start < timeout:
            time.sleep(0.1)
            
        if not self.connected:
            raise ConnectionError("Deepgram STT connection failed")
            
    def _on_open(self, ws):
        print("[STT] Connected!")
        self.connected = True
        
    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
            if "channel" in data and "alternatives" in data["channel"]:
                transcript = data["channel"]["alternatives"][0].get("transcript", "")
                is_final = data.get("is_final", False)
                speech_final = data.get("speech_final", False)
                if transcript:
                    self.on_transcript(transcript, is_final, speech_final)
        except Exception as e:
            pass
            
    def _on_error(self, ws, error):
        print(f"[STT Error]: {error}")
        
    def _on_close(self, ws, close_status_code, close_msg):
        self.connected = False
        
    def send_audio(self, audio_chunk):
        if self.connected and self.ws:
            try:
                self.ws.send(audio_chunk, opcode=websocket.ABNF.OPCODE_BINARY)
            except:
                pass
                
    def close(self):
        if self.ws:
            self.ws.close()

# ==================== AUDIO CAPTURE ====================
class AudioCapture:
    def __init__(self, on_audio):
        self.on_audio = on_audio
        self.running = False
        
    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._capture)
        self.thread.daemon = True
        self.thread.start()
        print("[AUDIO] Started")
        
    def _capture(self):
        chunk = 1024
        audio = pyaudio.PyAudio()
        
        stream = audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=chunk,
        )
        
        print("[AUDIO] Listening... SPEAK NOW!")
        
        try:
            while self.running:
                data = stream.read(chunk, exception_on_overflow=False)
                self.on_audio(data)
        except Exception as e:
            print(f"[Audio Error]: {e}")
        finally:
            stream.stop_stream()
            stream.close()
            audio.terminate()
            
    def stop(self):
        self.running = False

# ==================== MAIN ====================
def main():
    agent = FastPhoneAgent(OPENROUTER_API_KEY)
    
    print('[STEP 4] Loading database...')
    df = pd.read_csv(PRODUCTS_CSV_PATH)
    conn = sqlite3.connect(':memory:', check_same_thread=False)
    df.to_sql('inventory', conn, if_exists='replace', index=False)
    print(f'[STEP 4] Database loaded! {len(df)} products\n')
    
    # Play greeting
    greeting = "Hello! I'm Taaniya from KGP Marketplace, your personal shopping assistant. We have over 150 products across 25 categories. What are you looking for today?"
    
    if START_AUDIO_PATH.exists():
        try:
            play(AudioSegment.from_mp3(str(START_AUDIO_PATH)))
        except:
            speak(greeting)
    else:
        speak(greeting)
    
    print("\n" + "="*55)
    print("🎙️  SPEAK NOW — I'm listening!")
    print("="*55 + "\n")
    
    is_finals = []
    should_exit = False
    processing = False
    last_spoken = ""
    pending_buy_more = False
    
    # Keywords to detect user wants to stop
    GOODBYE_KEYWORDS = ["bye", "goodbye", "that's all", "i'm done", "nothing else", "no more", "all done", "see you"]
    YES_KEYWORDS = ["yes", "yeah", "sure", "yep", "okay", "ok", "ya"]
    NO_KEYWORDS = ["no", "nope", "nah", "not now", "i'm good"]
    
    def on_transcript(text, is_final, speech_final):
        nonlocal is_finals, should_exit, processing, last_spoken, pending_buy_more
        
        if not text:
            return
            
        if is_final:
            is_finals.append(text)
            
            if speech_final:
                if processing:
                    return
                processing = True
                
                utterance = " ".join(is_finals).lower()
                print(f"\n🎤  {utterance}")
                
                def process():
                    nonlocal should_exit, processing, last_spoken, pending_buy_more
                    total_start = time.time()
                    
                    try:
                        # === HANDLE BUY MORE RESPONSE ===
                        if pending_buy_more:
                            if any(k in utterance for k in NO_KEYWORDS + GOODBYE_KEYWORDS):
                                goodbye = "Thank you for shopping at KGP Marketplace! Have a great day. EXIT"
                                print(f"🤖  {goodbye}")
                                speak(goodbye)
                                should_exit = True
                                return
                            elif any(k in utterance for k in YES_KEYWORDS):
                                pending_buy_more = False
                                response = "Awesome! What else would you like to buy?"
                                print(f"🤖  {response}")
                                speak(response)
                                return
                            else:
                                # User said a product name, treat as normal
                                pending_buy_more = False
                        
                        # === NORMAL AI FLOW ===
                        response = agent.get_reply(utterance, max_tokens=100)
                        
                        # === SQL HANDLING ===
                        while response.strip().startswith("SQL:"):
                            sql_lines = response.strip().split('\n')
                            sql_query = sql_lines[0][4:].strip()
                            
                            print(f"    🔍 SQL: {sql_query}")
                            
                            sql_start = time.time()
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
                                        stock = row.get('Stock', 'N/A')
                                        rows.append(f"{name} by {brand}: ₹{price} (Stock: {stock})")
                                    sql_response = "SQL Response:\n" + "\n".join(rows)
                                    
                            except Exception as e:
                                sql_response = f"SQL Error: {e}"
                            
                            sql_time = time.time() - sql_start
                            print(f"    📊 SQL: {sql_time:.3f}s | {len(result_df)} rows")
                            
                            response = agent.get_reply(sql_response, max_tokens=120)
                        
                        # === CLEAN RESPONSE ===
                        clean_response = response.strip()
                        
                        # === FIX INAPPROPRIATE EXIT ===
                        # If AI said EXIT but user didn't say goodbye, remove it
                        if 'EXIT' in clean_response:
                            if not any(k in utterance for k in GOODBYE_KEYWORDS):
                                clean_response = clean_response.replace('EXIT', '').strip()
                                # If it now doesn't ask to continue, add it
                                if "anything else" not in clean_response.lower() and "buy more" not in clean_response.lower():
                                    clean_response += " Would you like to buy anything else?"
                                    pending_buy_more = True
                        
                        # === AUTO-ADD BUY MORE QUESTION ===
                        # If AI confirmed order/payment but didn't ask to continue
                        order_signals = ["total comes out", "order is confirmed", "transaction is complete", 
                                       "you've paid", "payment received", "order confirmed", "here's your receipt"]
                        if any(sig in clean_response.lower() for sig in order_signals):
                            if "anything else" not in clean_response.lower() and "buy more" not in clean_response.lower() and 'EXIT' not in clean_response:
                                clean_response += " Would you like to buy anything else?"
                                pending_buy_more = True
                        
                        # === PRINT & SPEAK ===
                        if clean_response and clean_response != last_spoken:
                            print(f"🤖  {clean_response}")
                            speak(clean_response)
                            last_spoken = clean_response
                        
                        # === FINAL EXIT CHECK ===
                        if 'EXIT' in clean_response:
                            should_exit = True
                            print(f"\n👋  Session ending...")
                        
                        total_time = time.time() - total_start
                        print(f"    ⚡ TOTAL: {total_time:.2f}s")
                            
                    finally:
                        processing = False
                
                threading.Thread(target=process, daemon=True).start()
                is_finals = []
                    
        return False
    
    stt = DeepgramSTT(DEEPGRAM_API_KEY, on_transcript)
    
    try:
        stt.connect()
    except Exception as e:
        print(f"[FATAL] Deepgram failed: {e}")
        return
    
    def on_audio(data):
        stt.send_audio(data)
        
    capture = AudioCapture(on_audio)
    capture.start()
    
    try:
        while not should_exit:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        capture.stop()
        stt.close()
        tts_queue.put(None)
        conn.close()
        print("✅  Finished")

if __name__ == "__main__":
    main()