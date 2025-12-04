import os, requests, json

API_KEY = "YOUR_WHISPER_API_KEY"  # <-- Replace with your Whisper API key
BASE_URL = "https://api.whisper-api.com/transcribe"

os.makedirs("audio", exist_ok=True)

with open("urls.txt") as f:
    urls = [u.strip() for u in f if u.strip()]

for url in urls:
    filename = url.split("/")[-1].split("?")[0]
    name, ext = os.path.splitext(filename)
    folder = os.path.join("audio", name)
    os.makedirs(folder, exist_ok=True)

    audio_path = os.path.join(folder, filename)
    json_path = os.path.join(folder, f"{name}.json")

    if not os.path.exists(audio_path):
        r = requests.get(url)
        with open(audio_path, "wb") as f:
            f.write(r.content)

    with open(audio_path, "rb") as f:
        files = {"file": f}
        data = {
            "format": "json",
            "word_timestamps": "true",
            "language": "en"
        }
        headers = {"X-API-Key": API_KEY}
        resp = requests.post(BASE_URL, headers=headers, files=files, data=data)

    if resp.status_code == 200:
        json_data = resp.json()
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        print(f"✅ Transcribed: {filename}")
    else:
        print(f"❌ Error transcribing {filename}: {resp.text}")

print("All done! Commit & push to GitHub to store everything online.")
