from django.shortcuts import render, redirect
from django.db import connection
from .services import search_ebay_items
from django.contrib.auth.decorators import login_required
from datetime import date

# Create your views here.
def index(request):
    inventory_list = [] # 先準備一個空籃子
    
    if request.user.is_authenticated:
        with connection.cursor() as cursor:
            # 1. 去資料庫撈屬於這個使用者的收藏，包含圖片和最新行情
            sql = """
                SELECT p.name, p.imgurl, ui.purchase_price, ui.purchase_date,
                       COALESCE((SELECT market_price FROM price_histories 
                                WHERE product_id = p.id 
                                ORDER BY recorded_at DESC LIMIT 1), ui.purchase_price) AS market_price
                FROM user_inventories ui
                JOIN products p ON ui.product_id = p.id
                WHERE ui.user_id = %s
            """
            cursor.execute(sql, [request.user.id])
            rows = cursor.fetchall()
            
            # 2. 把撈到的資料整理好
            for row in rows:
                inventory_list.append({
                    'name': row[0],
                    'image': row[1],
                    'buy_price': row[2],
                    'buy_date': row[3],
                    'now_price': row[4],
                })
    
    # 3. 關鍵在這：要把 inventory_list 塞進最後一個參數 (把菜放到桌上)
    return render(request, 'tracker/index.html', {'inventory': inventory_list})

@login_required
def search_product(request):
    query = request.GET.get('q')
    results = []
    if query:
        # 呼叫我們剛剛寫好的 eBay 抓取服務
        results = search_ebay_items(query)
    return render(request, 'tracker/search.html', {'results': results, 'query': query})

@login_required
def add_to_inventory(request):
    if request.method == 'GET':
        # 顯示確認頁面，讓用戶輸入 quantity 和 purchase_price
        external_id = request.GET.get('external_id')
        name = request.GET.get('name')
        price = request.GET.get('price')
        image_url = request.GET.get('image_url')
        
        context = {
            'external_id': external_id,
            'name': name,
            'price': price,
            'image_url': image_url,
        }
        return render(request, 'tracker/add_confirm.html', context)
    
    elif request.method == 'POST':
        # 獲取前端傳過來的商品資料
        ext_id = request.POST.get('external_id')
        name = request.POST.get('name')
        price = request.POST.get('price')
        image_url = request.POST.get('image_url')
        purchase_price = request.POST.get('purchase_price')
        quantity = request.POST.get('quantity', 1)
        user_id = request.user.id

        with connection.cursor() as cursor:
            # 1. 檢查並插入 Product (如果不存在)
            cursor.execute("""
                INSERT OR IGNORE INTO products (name, external_id, category, imgurl)
                VALUES (%s, %s, %s, %s)
            """, [name, ext_id, 'Collectible', image_url])
            
            # 獲取該產品在我們資料庫的真正 ID
            cursor.execute("SELECT id FROM products WHERE external_id = %s", [ext_id])
            product_id = cursor.fetchone()[0]
            
            # 更新 imgurl 確保有圖片
            cursor.execute("""
                UPDATE products SET imgurl = %s WHERE id = %s
            """, [image_url, product_id])

            # 2. 存入 PriceHistory (紀錄當下行情)
            cursor.execute("""
                INSERT INTO price_histories (product_id, market_price, recorded_at)
                VALUES (%s, %s, datetime('now'))
            """, [product_id, price])

            # 3. 存入 UserCollection (建立使用者的收藏紀錄)
            cursor.execute("""
                INSERT INTO user_inventories (user_id, product_id, purchase_price, purchase_date, quantity)
                VALUES (%s, %s, %s, %s, %s)
            """, [user_id, product_id, purchase_price, date.today(), quantity])

        return redirect('index')