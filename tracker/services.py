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
        "limit": 30  # 先抓 30 筆給使用者挑選
    }

    response = requests.get(search_url, headers=headers, params=params)
    print(f"--- Search Request Status: {response.status_code} ---")
    print(f"Search Response: {response.json()}") # 這是最重要的一行
    data = response.json()
    
    # 整理成我們資料庫好讀的格式
    results = []
    for item in data.get('itemSummaries', []):
        category_name = 'Other'
        categories = item.get('categories', [])
        if categories:
            # 優先拿取 eBay 回傳的第一個分類名稱
            category_name = categories[0].get('categoryName', 'Other')
            
        results.append({
            'external_id': item.get('itemId'),
            'name': item.get('title'),
            'price': item.get('price', {}).get('value'),
            'currency': item.get('price', {}).get('currency'),
            'image_url': item.get('thumbnailImages', [{}])[0].get('imageUrl'),
            'platform': 'eBay',
            'category': category_name
        })
    return results

def search_ptcg_cards(keyword):
    # 使用 Pokemon TCG API (免授權碼可基本搜尋)
    search_url = "https://api.pokemontcg.io/v2/cards"
    
    # 建立「多重單字模糊比對」的漸進式搜尋策略
    # 1. 允許不分順序的比對 (例如輸入 "VMAX Charizard" 也找得到)
    # 2. 若找不到，從後面依序拿掉單字再試 (例如過濾掉 "PSA 10")
    words = keyword.split() if keyword else []
    
    queries_to_try = []
    for i in range(len(words), 0, -1):
        subset = words[:i]
        # 轉換成 Lucene 多重模糊搜尋語法，例如：name:*Charizard* name:*VMAX*
        q = ' '.join([f"name:*{w}*" for w in subset])
        queries_to_try.append(q)
        
    data = []
    results = []
    try:
        for q in queries_to_try:
            params = {
                "q": q,
                "pageSize": 10
            }
            response = requests.get(search_url, params=params)
            if response.status_code == 200:
                current_data = response.json().get('data', [])
                if current_data:
                    data = current_data
                    break # 一旦找到結果就停止嘗試更寬鬆的條件
        for card in data:
            price = 0
            currency = 'USD'
            
            # 優先嘗試取得 TCGPlayer 行情
            tcg_prices = card.get('tcgplayer', {}).get('prices', {})
            if tcg_prices:
                # 嘗試抓取各種版本的 market price
                for variant in ['holofoil', 'normal', 'reverseHolofoil', '1stEditionHolofoil', 'unlimitedHolofoil']:
                    if variant in tcg_prices and tcg_prices[variant].get('market'):
                        price = tcg_prices[variant]['market']
                        break
            
            # 若無 TCGPlayer 價格，則取 Cardmarket 價格
            if not price:
                cardmarket = card.get('cardmarket', {}).get('prices', {})
                if cardmarket.get('averageSellPrice'):
                    price = cardmarket.get('averageSellPrice')
                    currency = 'EUR'
                    
            set_name = card.get('set', {}).get('name', 'Unknown Set')
            
            results.append({
                'external_id': card.get('id'),
                'name': f"{card.get('name')} ({set_name})",
                'price': price,
                'currency': currency,
                'image_url': card.get('images', {}).get('small'),
                'platform': 'PTCG API',
                'category': 'Pokémon Cards'
            })
        return results
    except Exception as e:
        print(f"PTCG API 錯誤: {e}")
        return []

def get_ptcg_card_price(external_id):
    url = f"https://api.pokemontcg.io/v2/cards/{external_id}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            card = response.json().get('data', {})
            price = 0
            tcg_prices = card.get('tcgplayer', {}).get('prices', {})
            if tcg_prices:
                for variant in ['holofoil', 'normal', 'reverseHolofoil', '1stEditionHolofoil', 'unlimitedHolofoil']:
                    if variant in tcg_prices and tcg_prices[variant].get('market'):
                        price = tcg_prices[variant]['market']
                        break
            if not price:
                cardmarket = card.get('cardmarket', {}).get('prices', {})
                if cardmarket.get('averageSellPrice'):
                    price = cardmarket.get('averageSellPrice')
            return price
    except Exception as e:
        print(f"PTCG API Price Update Error: {e}")
    return 0

def get_ebay_average_price(name):
    # 使用現有的搜尋函式取得最新搜尋結果
    results = search_ebay_items(name)
    prices = []
    for item in results:
        try:
            # 確保價格存在且可轉換為 float
            if item.get('price'):
                prices.append(float(item['price']))
        except (ValueError, TypeError):
            continue
            
    if prices:
        # 去除極端值邏輯：如果抓到的價格數量大於等於 4 筆，排序後切掉最高與最低價 (Trimmed Mean)
        if len(prices) >= 4:
            prices.sort()
            valid_prices = prices[1:-1]
        else:
            valid_prices = prices
            
        return round(sum(valid_prices) / len(valid_prices), 2)
    return 0


def fetch_ptcg_news():
    """
    從 Google News RSS 抓取 PTCG / Pokemon TCG 相關新聞。
    使用 Python 內建的 xml.etree.ElementTree 解析 XML，不需額外安裝套件。
    回傳最多 10 則新聞：[{title, link, source, published}]
    """
    import xml.etree.ElementTree as ET
    from datetime import datetime

    rss_url = "https://news.google.com/rss/search?q=Pokemon+TCG+OR+PTCG+OR+%E5%AF%B6%E5%8F%AF%E5%A4%A2%E5%8D%A1%E7%89%8C&hl=en&gl=US&ceid=US:en"

    try:
        response = requests.get(rss_url, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        if response.status_code != 200:
            print(f"Google News RSS failed: {response.status_code}")
            return []

        root = ET.fromstring(response.content)
        channel = root.find('channel')
        if channel is None:
            return []

        news_list = []
        for item in channel.findall('item')[:10]:
            title = item.findtext('title', '')
            link = item.findtext('link', '')
            pub_date_str = item.findtext('pubDate', '')
            source_el = item.find('source')
            source = source_el.text if source_el is not None else 'Unknown'

            # 解析發佈時間
            published = pub_date_str
            try:
                # Google News RSS 格式: "Fri, 23 May 2026 08:00:00 GMT"
                dt = datetime.strptime(pub_date_str, '%a, %d %b %Y %H:%M:%S %Z')
                # 計算多久前
                diff = datetime.utcnow() - dt
                if diff.days > 0:
                    published = f"{diff.days}d ago"
                elif diff.seconds >= 3600:
                    published = f"{diff.seconds // 3600}h ago"
                elif diff.seconds >= 60:
                    published = f"{diff.seconds // 60}m ago"
                else:
                    published = "just now"
            except (ValueError, TypeError):
                pass  # 保留原始字串

            news_list.append({
                'title': title,
                'link': link,
                'source': source,
                'published': published,
            })

        return news_list

    except Exception as e:
        print(f"Fetch PTCG news error: {e}")
        return []