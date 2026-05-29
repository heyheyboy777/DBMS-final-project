#處理外部 API
import re
import time
import requests
import base64
from django.conf import settings

TIMEOUT = 8  # 所有外部 API 請求的統一上限（秒）

# 快取 eBay token，避免每次搜尋都重新拿（token 有效期約 2 小時）
_ebay_token_cache = {'token': None, 'expires_at': 0}

def get_ebay_token():
    if _ebay_token_cache['token'] and time.time() < _ebay_token_cache['expires_at']:
        return _ebay_token_cache['token']

    auth_str = f"{settings.EBAY_CLIENT_ID}:{settings.EBAY_CLIENT_SECRET}"
    b64_auth = base64.b64encode(auth_str.encode()).decode()

    try:
        response = requests.post(
            "https://api.ebay.com/identity/v1/oauth2/token",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {b64_auth}",
            },
            data={
                "grant_type": "client_credentials",
                "scope": "https://api.ebay.com/oauth/api_scope",
            },
            timeout=TIMEOUT,
        )
        resp_json = response.json()
    except Exception as e:
        print(f"eBay token error: {e}")
        return None

    token = resp_json.get('access_token')
    expires_in = resp_json.get('expires_in', 7200)
    _ebay_token_cache['token'] = token
    _ebay_token_cache['expires_at'] = time.time() + expires_in - 60
    return token

def search_ebay_items(keyword):
    token = get_ebay_token()
    if not token:
        return []

    try:
        response = requests.get(
            "https://api.ebay.com/buy/browse/v1/item_summary/search",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            params={"q": keyword, "limit": 30},
            timeout=TIMEOUT,
        )
        data = response.json()
    except Exception as e:
        print(f"eBay search error: {e}")
        return []

    results = []
    for item in data.get('itemSummaries', []):
        categories = item.get('categories', [])
        category_name = categories[0].get('categoryName', 'Other') if categories else 'Other'
        results.append({
            'external_id': item.get('itemId'),
            'name': item.get('title'),
            'price': item.get('price', {}).get('value'),
            'currency': item.get('price', {}).get('currency'),
            'image_url': item.get('thumbnailImages', [{}])[0].get('imageUrl'),
            'platform': 'eBay',
            'category': category_name,
        })
    return results

def search_ptcg_cards(keyword):
    search_url = "https://api.pokemontcg.io/v2/cards"

    if not keyword:
        return []

    # 去掉括號及其內容（顯示用的 "(Set Name)" 不是卡名）
    keyword = re.sub(r'\(.*?\)', '', keyword)
    # 去掉 Lucene 特殊字元，避免 API 查詢語法錯誤
    keyword = re.sub(r"[()'\"+~^:!{}\[\]\\]", ' ', keyword).strip()

    if not keyword:
        return []

    # 評級機構、品相描述詞不是卡名的一部分，先濾掉再送 API
    NOISE = {'psa', 'bgs', 'cgc', 'sgc', 'beckett', 'graded', 'mint', 'gem', 'near', 'raw', 'sealed'}
    all_words = keyword.split()
    clean_words = [
        w for w in all_words
        if w.lower() not in NOISE and not (w.isdigit() and int(w) <= 12)
    ]
    words = clean_words if clean_words else all_words

    data = []
    try:
        # 第一步：所有詞 AND 查詢卡名
        q = ' '.join([f"name:*{w}*" for w in words])
        resp = requests.get(search_url, params={"q": q, "pageSize": 30}, timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json().get('data', [])

        # 第二步：AND 查詢無結果時，只用最長的詞查，拉多一點再客戶端排序
        if not data:
            longest = max(words, key=len)
            resp = requests.get(search_url, params={"q": f"name:*{longest}*", "pageSize": 30}, timeout=TIMEOUT)
            if resp.status_code == 200:
                data = resp.json().get('data', [])

        # 依相關性排序：命中越多搜尋詞的卡排越前面
        search_lower = [w.lower() for w in words]
        data.sort(key=lambda card: sum(1 for w in search_lower if w in card.get('name', '').lower()), reverse=True)

        results = []
        for card in data:
            price = 0
            currency = 'USD'

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
                    currency = 'EUR'

            set_name = card.get('set', {}).get('name', 'Unknown Set')
            results.append({
                'external_id': card.get('id'),
                'name': f"{card.get('name')} ({set_name})",
                'price': price,
                'currency': currency,
                'image_url': card.get('images', {}).get('small'),
                'platform': 'PTCG API',
                'category': 'Pokémon Cards',
            })
        return results
    except Exception as e:
        print(f"PTCG API 錯誤: {e}")
        return []

def get_ptcg_card_price(external_id):
    try:
        resp = requests.get(f"https://api.pokemontcg.io/v2/cards/{external_id}", timeout=TIMEOUT)
        if resp.status_code == 200:
            card = resp.json().get('data', {})
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
    results = search_ebay_items(name)
    prices = []
    for item in results:
        try:
            if item.get('price'):
                prices.append(float(item['price']))
        except (ValueError, TypeError):
            continue

    if prices:
        if len(prices) >= 4:
            prices.sort()
            valid_prices = prices[1:-1]
        else:
            valid_prices = prices
        return round(sum(valid_prices) / len(valid_prices), 2)
    return 0


def fetch_ptcg_news():
    import xml.etree.ElementTree as ET
    from datetime import datetime

    rss_url = "https://news.google.com/rss/search?q=Pokemon+TCG+OR+PTCG+OR+%E5%AF%B6%E5%8F%AF%E5%A4%A2%E5%8D%A1%E7%89%8C&hl=en&gl=US&ceid=US:en"

    try:
        response = requests.get(rss_url, timeout=TIMEOUT, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        if response.status_code != 200:
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

            published = pub_date_str
            try:
                dt = datetime.strptime(pub_date_str, '%a, %d %b %Y %H:%M:%S %Z')
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
                pass

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
