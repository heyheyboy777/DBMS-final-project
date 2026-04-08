#處理外部 API
import requests
import base64
from django.conf import settings

def get_ebay_token():
    # 使用你截圖中的 Sandbox Client ID 和 Secret
    auth_str = f"{settings.EBAY_CLIENT_ID}:{settings.EBAY_CLIENT_SECRET}"
    b64_auth = base64.b64encode(auth_str.encode()).decode()

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {b64_auth}"
    }
    
    url = "https://api.ebay.com/identity/v1/oauth2/token"
    data = {
        "grant_type": "client_credentials",
        "scope": "https://api.ebay.com/oauth/api_scope"
    }

    response = requests.post(url, headers=headers, data=data)
    print(f"--- Token Request Status: {response.status_code} ---")
    print(f"Token Response: {response.json()}") # 看看有沒有報錯
    return response.json().get('access_token')

def search_ebay_items(keyword):
    token = get_ebay_token()
    if not token:
        print("!!! 無法取得 Token，請檢查 Client ID 和 Secret !!!")
        return []

    # 使用 eBay Browse API 搜尋商品 (Sandbox 環境)
    search_url = "https://api.ebay.com/buy/browse/v1/item_summary/search"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    params = {
        "q": keyword,
        "limit": 5  # 先抓 5 筆給使用者挑選
    }

    response = requests.get(search_url, headers=headers, params=params)
    print(f"--- Search Request Status: {response.status_code} ---")
    print(f"Search Response: {response.json()}") # 這是最重要的一行
    data = response.json()
    
    # 整理成我們資料庫好讀的格式
    results = []
    for item in data.get('itemSummaries', []):
        results.append({
            'external_id': item.get('itemId'),
            'name': item.get('title'),
            'price': item.get('price', {}).get('value'),
            'currency': item.get('price', {}).get('currency'),
            'image_url': item.get('thumbnailImages', [{}])[0].get('imageUrl')
        })
    return results