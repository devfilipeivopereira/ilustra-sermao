import requests
import json

TOKEN = "3hIhvSE7QI09a294yaW73wtt"
BASE_URL = "https://api-us.storyblok.com/v2/cdn/stories"

def list_content_types():
    params = {
        "version": "published",
        "per_page": 100,
        "token": TOKEN,
    }
    
    response = requests.get(BASE_URL, params=params)
    data = response.json()
    
    # Vamos pegar uma amostra maior para ver diferentes prefixos de slug
    folders = set()
    components = set()
    
    if data.get("stories"):
        for story in data["stories"]:
            full_slug = story.get("full_slug", "")
            if "/" in full_slug:
                folder = full_slug.split("/")[0]
                folders.add(folder)
            
            component = story.get("content", {}).get("component")
            if component:
                components.add(component)
                
    print(f"Pastas encontradas: {folders}")
    print(f"Componentes encontrados: {components}")

    # Tentar buscar por pastas específicas comuns
    potential_folders = ["series", "sermons", "commentary", "quotes", "liturgy", "blog"]
    for folder in potential_folders:
        params["starts_with"] = folder + "/"
        res = requests.get(BASE_URL, params=params)
        if res.status_code == 200:
            count = res.headers.get("total", "0")
            print(f"Pasta '{folder}': {count} itens")

if __name__ == "__main__":
    list_content_types()
