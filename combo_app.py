import streamlit as st
import os
import re
import time
import json
import uuid
from collections import Counter
from datetime import datetime, timedelta
import aiohttp
import asyncio

# File to store keys and user data
KEYS_FILE = "keys.json"
USER_PREFS_FILE = "user_prefs.json"

# Admin ID (replace with a unique identifier, e.g., your email or a UUID)
ADMIN_ID = "malgus"  # Replace with a unique identifier for yourself

# Load or initialize keys and user preferences
def load_keys():
    if os.path.exists(KEYS_FILE):
        with open(KEYS_FILE, 'r') as f:
            return json.load(f)
    return {"keys": {}, "used_keys": []}

def save_keys(keys_data):
    with open(KEYS_FILE, 'w') as f:
        json.dump(keys_data, f, indent=4)

def load_user_prefs():
    if os.path.exists(USER_PREFS_FILE):
        with open(USER_PREFS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_user_prefs(prefs):
    with open(USER_PREFS_FILE, 'w') as f:
        json.dump(prefs, f, indent=4)

keys_data = load_keys()
user_prefs = load_user_prefs()

async def send_to_webhook(webhook_url, message, file_path, filename):
    """Send combo stats and file to the specified webhook"""
    try:
        async with aiohttp.ClientSession() as session:
            with open(file_path, 'rb') as f:
                form = aiohttp.FormData()
                form.add_field('file', f, filename=filename)
                form.add_field('message', message)
                async with session.post(webhook_url, data=form) as response:
                    if response.status == 200:
                        st.success(f"Sent to webhook {webhook_url}")
                    else:
                        st.error(f"Webhook error {webhook_url}: {response.status}")
                        return f"Webhook error: {response.status}"
    except Exception as e:
        st.error(f"Webhook error {webhook_url}: {e}")
        return str(e)
    return None

def clean_and_count_combos(filepath, min_combo_count, keywords):
    """Extract unique valid email:password combos and analyze domains"""
    email_regex = r'^([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,}):.+$'
    unique_combos = set()
    domain_counter = Counter()
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if match := re.match(email_regex, line):
                    unique_combos.add(line)
                    domain = match.group(2).lower()
                    domain_counter[domain] += 1
        
        combo_count = len(unique_combos)
        
        if combo_count >= min_combo_count:
            return combo_count, unique_combos, domain_counter
        else:
            st.warning(f"File has only {combo_count} combos (minimum required: {min_combo_count})")
            return combo_count, None, domain_counter
            
    except Exception as e:
        st.error(f"Error processing combos: {e}")
        return 0, None, None

async def process_file(file, user_id):
    """Process uploaded file"""
    prefs = user_prefs.get(user_id, {})
    keywords = prefs.get("keywords", ['hotmail', 'microsoft', 'combo', 'outlook', 'mixed', 'piece'])
    keyword_pattern = re.compile('|'.join(map(re.escape, keywords)), re.IGNORECASE)
    min_combo_count = prefs.get("min_combo_count", 200)
    output_filename = prefs.get("output_filename", "cleaned_combos.txt")
    message_template = prefs.get("message_template", (
        "🔥 New Combo Drop!\n\n"
        "📊 Total Lines: {count:,}\n"
        "🏆 Top Domains:\n"
        "{domains}"
        "\n💾 Cleaned combo file attached"
    ))
    
    filename = file.name
    if not keyword_pattern.search(filename.lower()):
        st.error(f"File '{filename}' does not match your keywords: {', '.join(keywords)}")
        return
    
    temp_path = os.path.join("temp", filename)
    os.makedirs("temp", exist_ok=True)
    
    with open(temp_path, 'wb') as f:
        f.write(file.read())
    
    count, unique_combos, top_domains = clean_and_count_combos(temp_path, min_combo_count, keywords)
    
    if unique_combos:
        cleaned_path = os.path.join("temp", output_filename)
        with open(cleaned_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(unique_combos))
        
        domains = ""
        for i, (domain, cnt) in enumerate(top_domains.most_common(5)):
            domains += f"   {i+1}. {domain}: {cnt:,}\n"
        
        message = message_template.format(count=count, domains=domains)
        
        notify = prefs.get("notify", True)
        if notify:
            st.text_area("Combo Stats", message, height=200)
            with open(cleaned_path, 'rb') as f:
                st.download_button(
                    label="Download Combos",
                    data=f,
                    file_name=output_filename,
                    mime="text/plain"
                )
        
        webhook_url = prefs.get("webhook_url")
        if webhook_url:
            await send_to_webhook(webhook_url, message, cleaned_path, output_filename)
        
        os.remove(cleaned_path)
    else:
        st.error(f"File has only {count} combos (minimum required: {min_combo_count})")
    
    os.remove(temp_path)

def main():
    st.title("Combo Processing App")
    
    # Session state for user authentication
    if 'user_id' not in st.session_state:
        st.session_state.user_id = None
    
    if st.session_state.user_id is None:
        st.header("Login")
        key = st.text_input("Enter your key")
        if st.button("Redeem Key"):
            keys_data = load_keys()
            if key in keys_data["used_keys"]:
                st.error("This key has already been used!")
            elif key not in keys_data["keys"]:
                st.error("Invalid key!")
            elif keys_data["keys"][key]["expires_at"] and keys_data["keys"][key]["expires_at"] < time.time():
                st.error("This key has expired!")
            else:
                user_id = str(uuid.uuid4())  # Generate a unique user ID
                keys_data["used_keys"].append(key)
                keys_data["keys"][key]["user_id"] = user_id
                save_keys(keys_data)
                
                user_prefs[user_id] = {
                    "notify": True,
                    "keywords": ['hotmail', 'microsoft', 'combo', 'outlook', 'mixed', 'piece'],
                    "webhook_url": None,
                    "min_combo_count": 200,
                    "output_filename": "cleaned_combos.txt",
                    "message_template": (
                        "🔥 New Combo Drop!\n\n"
                        "📊 Total Lines: {count:,}\n"
                        "🏆 Top Domains:\n"
                        "{domains}"
                        "\n💾 Cleaned combo file attached"
                    )
                }
                save_user_prefs(user_prefs)
                st.session_state.user_id = user_id
                st.success("Key redeemed successfully! You can now use the app.")
                st.rerun()
    
    elif st.session_state.user_id == ADMIN_ID:
        st.header("Admin Panel")
        admin_option = st.selectbox("Select Action", ["Generate Keys", "List Keys", "Revoke Key"])
        
        if admin_option == "Generate Keys":
            count = st.number_input("Number of keys", min_value=1, value=1)
            days = st.number_input("Expiration days", min_value=1, value=30)
            if st.button("Generate"):
                keys_data = load_keys()
                expires_at = (datetime.now() + timedelta(days=days)).timestamp()
                new_keys = [str(uuid.uuid4()) for _ in range(count)]
                for key in new_keys:
                    keys_data["keys"][key] = {"user_id": None, "expires_at": expires_at}
                save_keys(keys_data)
                expires_date = datetime.fromtimestamp(expires_at).strftime("%Y-%m-%d %H:%M:%S")
                st.success(f"Generated {count} keys (expire on {expires_date}):\n" + "\n".join(new_keys))
        
        elif admin_option == "List Keys":
            keys_data = load_keys()
            keys_list = "\n".join(
                f"{key}: {'Used by ' + keys_data['keys'][key]['user_id'] if keys_data['keys'][key]['user_id'] else 'Unused'}, "
                f"Expires: {datetime.fromtimestamp(keys_data['keys'][key]['expires_at']).strftime('%Y-%m-%d %H:%M:%S') if keys_data['keys'][key]['expires_at'] else 'Never'}"
                for key in keys_data["keys"]
            ) or "No keys available."
            st.text_area("Keys", keys_list, height=200)
        
        elif admin_option == "Revoke Key":
            key = st.text_input("Enter key to revoke")
            if st.button("Revoke"):
                keys_data = load_keys()
                if key in keys_data["keys"]:
                    user_id = keys_data["keys"][key]["user_id"]
                    if user_id:
                        keys_data["used_keys"].remove(key)
                        keys_data["Keys"][key]["user_id"] = None
                        save_keys(keys_data)
                        if user_id in user_prefs:
                            del user_prefs[user_id]
                            save_user_prefs(user_prefs)
                        st.success(f"Key {key} revoked.")
                    else:
                        st.warning("Key is unused.")
                else:
                    st.error("Invalid key.")
    
    else:
        st.header("User Dashboard")
        user_id = st.session_state.user_id
        prefs = user_prefs.get(user_id, {})
        
        st.subheader("Settings")
        notify = st.checkbox("Enable Notifications", value=prefs.get("notify", True))
        keywords = st.text_input("Keywords (comma-separated)", value=", ".join(prefs.get("keywords", ['hotmail', 'microsoft', 'combo', 'outlook', 'mixed', 'piece'])))
        webhook_url = st.text_input("Webhook URL (optional)", value=prefs.get("webhook_url", "") or "")
        min_combo_count = st.number_input("Minimum Combo Count", min_value=1, value=prefs.get("min_combo_count", 200))
        output_filename = st.text_input("Output Filename", value=prefs.get("output_filename", "cleaned_combos.txt"))
        message_template = st.text_area("Message Template (use {count} and {domains})", value=prefs.get("message_template", (
            "🔥 New Combo Drop!\n\n"
            "📊 Total Lines: {count:,}\n"
            "🏆 Top Domains:\n"
            "{domains}"
            "\n💾 Cleaned combo file attached"
        )), height=200)
        
        if st.button("Save Settings"):
            if not keywords.strip():
                st.error("Keywords cannot be empty.")
            else:
                user_prefs[user_id] = {
                    "notify": notify,
                    "keywords": [k.strip().lower() for k in keywords.split(",") if k.strip()],
                    "webhook_url": webhook_url if webhook_url.strip() else None,
                    "min_combo_count": min_combo_count,
                    "output_filename": output_filename if output_filename.endswith(".txt") else output_filename + ".txt",
                    "message_template": message_template.strip()
                }
                save_user_prefs(user_prefs)
                st.success("Settings saved!")
        
        st.subheader("Upload File")
        file = st.file_uploader("Upload a combo file", type=["txt"])
        if file and st.button("Process File"):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(process_file(file, user_id))
            finally:
                loop.close()

if __name__ == "__main__":
    main()