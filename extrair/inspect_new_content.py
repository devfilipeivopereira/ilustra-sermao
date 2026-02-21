import requests
import json

TOKEN = "3hIhvSE7QI09a294yaW73wtt"
BASE_URL = "https://api-us.storyblok.com/v2/cdn/stories"

def inspect(folder):
    params = {
        "version": "published",
        "per_page": 1,
        "token": TOKEN,
        "starts_with": folder + "/",
        "is_startpage": 0
    }
    
    try:
        res = requests.get(BASE_URL, params=params, timeout=10)
        if res.status_code == 200:
            data = res.json()
            if data.get("stories"):
                story = data["stories"][0]
                with open(f"/home/ubuntu/sample_{folder}.json", "w", encoding="utf-8") as f:
                    json.dump(story, f, indent=2, ensure_ascii=False)
                print(f"Sample for '{folder}' saved.")
    except Exception as e:
        print(f"Error inspecting '{folder}': {e}")

if __name__ == "__main__":
    inspect("quotes")
    inspect("liturgy")
    inspect("series")
