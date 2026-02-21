import requests
import json

TOKEN = "3hIhvSE7QI09a294yaW73wtt"
BASE_URL = "https://api-us.storyblok.com/v2/cdn/stories"

def list_folders():
    params = {
        "version": "published",
        "per_page": 1,
        "token": TOKEN,
    }
    
    potential_folders = ["series", "sermons", "commentary", "quotes", "liturgy", "blog", "sermon-illustrations"]
    results = {}
    
    for folder in potential_folders:
        params["starts_with"] = folder + "/"
        try:
            res = requests.get(BASE_URL, params=params, timeout=10)
            if res.status_code == 200:
                count = res.headers.get("total", "0")
                results[folder] = count
                print(f"Folder '{folder}': {count} items")
            else:
                print(f"Folder '{folder}': Not found (Status {res.status_code})")
        except:
            print(f"Folder '{folder}': Timeout")
            
    return results

if __name__ == "__main__":
    list_folders()
