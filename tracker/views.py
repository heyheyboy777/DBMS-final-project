from django.shortcuts import render, redirect
from django.db import connection
from .services import search_ebay_items
from django.contrib.auth.decorators import login_required
from datetime import date

# Create your views here.
def index(request):
    return render(request, 'tracker/index.html')

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
    if request.method == 'POST':
        # 獲取前端傳過來的商品資料
        ext_id = request.POST.get('external_id')
        name = request.POST.get('name')
        price = request.POST.get('price')
        img_url = request.POST.get('image_url')
        user_id = request.user.id

        with connection.cursor() as cursor:
            # 1. 檢查並插入 Product (如果不存在)
            # 使用 Raw SQL 的 INSERT OR IGNORE 邏輯
            cursor.execute("""
                INSERT OR IGNORE INTO products (official_name, external_id, image_url, category)
                VALUES (%s, %s, %s, %s)
            """, [name, ext_id, img_url, 'Collectible'])

            # 獲取該產品在我們資料庫的真正 ID
            cursor.execute("SELECT id FROM products WHERE external_id = %s", [ext_id])
            product_id = cursor.fetchone()[0]

            # 2. 存入 PriceHistory (紀錄當下行情)
            cursor.execute("""
                INSERT INTO price_histories (product_id, market_price, recorded_at)
                VALUES (%s, %s, datetime('now'))
            """, [product_id, price])

            # 3. 存入 UserInventory (建立使用者的收藏紀錄)
            cursor.execute("""
                INSERT INTO user_inventories (user_id, product_id, purchase_price, purchase_date, quantity)
                VALUES (%s, %s, %s, %s, 1)
            """, [user_id, product_id, price, date.today()])

        return redirect('index') # 完成後回到首頁