from django.shortcuts import render, redirect
from django.db import connection
from .services import search_ebay_items, search_ptcg_cards, get_ptcg_card_price, get_ebay_average_price
from django.contrib.auth.decorators import login_required
from datetime import date
from .forms import UserProfileForm
from django.contrib import messages
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login

# Create your views here.
def index(request):
    inventory_list = [] # 先準備一個空籃子
    
    if request.user.is_authenticated:
        with connection.cursor() as cursor:
            # 1. 去資料庫撈屬於這個使用者的收藏，包含圖片和最新行情，並將相同的商品合併顯示數量
            sql = """
                SELECT p.id, p.name, p.imgurl, 
                       AVG(ui.purchase_price) AS avg_purchase_price, 
                       MAX(ui.purchase_date) AS latest_purchase_date,
                       
                       (SELECT market_price FROM price_histories 
                        WHERE product_id = p.id AND platform = 'PTCG API' 
                        ORDER BY recorded_at DESC LIMIT 1) AS ptcg_price,
                        
                       (SELECT market_price FROM price_histories 
                        WHERE product_id = p.id AND platform = 'eBay' 
                        ORDER BY recorded_at DESC LIMIT 1) AS ebay_price,
                        
                       SUM(ui.quantity) AS total_quantity,
                       p.category,
                       p.platform
                FROM user_inventories ui
                JOIN products p ON ui.product_id = p.id
                WHERE ui.user_id = %s
                GROUP BY p.id, p.name, p.imgurl, p.category, p.platform
            """
            cursor.execute(sql, [request.user.id])
            rows = cursor.fetchall()
            
            # 2. 把撈到的資料整理好
            for row in rows:
                product_id = row[0]
                name = row[1]
                image = row[2]
                avg_purchase = row[3]
                buy_date = row[4]
                ptcg_price = row[5]
                ebay_price = row[6]
                quantity = row[7]
                category = row[8]
                platform = row[9]
                
                if platform == 'eBay' and ebay_price is None:
                    ebay_price = avg_purchase
                    
                if platform == 'PTCG API' and ptcg_price is None:
                    ptcg_price = avg_purchase
                    
                inventory_list.append({
                    'product_id': product_id,
                    'name': name,
                    'image': image,
                    'buy_price': round(avg_purchase, 2) if avg_purchase else 0,
                    'buy_date': buy_date,
                    'ptcg_price': round(ptcg_price, 2) if ptcg_price else 0,
                    'ebay_price': round(ebay_price, 2) if ebay_price else None,
                    'quantity': quantity,
                    'category': category,
                    'platform': platform
                })
    
    # 3. 關鍵在這：要把 inventory_list 塞進最後一個參數 (把菜放到桌上)
    return render(request, 'tracker/index.html', {'inventory': inventory_list})

@login_required
def search_product(request):
    query = request.GET.get('q')
    search_ptcg = request.GET.get('search_ptcg') # 獲取 PTCG 搜尋開關狀態
    results = []
    if query:
        # 預設必定呼叫 eBay API
        ebay_results = search_ebay_items(query)
        
        if search_ptcg:
            # 如果開啟 ptcg 開關，才呼叫 PTCG API
            ptcg_results = search_ptcg_cards(query)
            # 將兩個平台的結果合併在一起顯示，PTCG 卡牌行情優先顯示在前面
            results = ptcg_results + ebay_results
        else:
            results = ebay_results
            
    return render(request, 'tracker/search.html', {'results': results, 'query': query, 'search_ptcg': search_ptcg})

@login_required
def add_to_inventory(request):
    if request.method == 'GET':
        # 顯示確認頁面，讓用戶輸入 quantity 和 purchase_price
        external_id = request.GET.get('external_id')
        name = request.GET.get('name')
        price = request.GET.get('price')
        image_url = request.GET.get('image_url')
        platform = request.GET.get('platform', 'eBay')
        category = request.GET.get('category', 'Other')
        
        context = {
            'external_id': external_id,
            'name': name,
            'price': price,
            'image_url': image_url,
            'platform': platform,
            'category': category,
        }
        return render(request, 'tracker/add_confirm.html', context)
    
    elif request.method == 'POST':
        # 獲取前端傳過來的商品資料
        ext_id = request.POST.get('external_id')
        name = request.POST.get('name')
        price = request.POST.get('price')
        image_url = request.POST.get('image_url')
        platform = request.POST.get('platform', 'eBay')
        category = request.POST.get('category', 'Other')
        purchase_price = request.POST.get('purchase_price')
        quantity = request.POST.get('quantity', 1)
        user_id = request.user.id

        with connection.cursor() as cursor:
            # 1. 檢查並插入 Product (如果不存在)
            cursor.execute("""
                INSERT OR IGNORE INTO products (name, external_id, category, platform, imgurl)
                VALUES (%s, %s, %s, %s, %s)
            """, [name, ext_id, category, platform, image_url])
            
            # 獲取該產品在我們資料庫的真正 ID
            cursor.execute("SELECT id FROM products WHERE external_id = %s", [ext_id])
            product_id = cursor.fetchone()[0]
            
            # 更新 imgurl 確保有圖片
            cursor.execute("""
                UPDATE products SET imgurl = %s WHERE id = %s
            """, [image_url, product_id])

            # 2. 存入 PriceHistory (紀錄當下行情)
            cursor.execute("""
                INSERT INTO price_histories (product_id, market_price, platform, recorded_at)
                VALUES (%s, %s, %s, datetime('now'))
            """, [product_id, price, platform])

            # 3. 存入 UserCollection (建立使用者的收藏紀錄)
            cursor.execute("""
                INSERT INTO user_inventories (user_id, product_id, purchase_price, purchase_date, quantity)
                VALUES (%s, %s, %s, %s, %s)
            """, [user_id, product_id, purchase_price, date.today(), quantity])

        return redirect('index')

@login_required
def profile(request):
    edit_mode = request.GET.get('edit') == '1'
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            user = form.save(commit=False)
            password = form.cleaned_data.get('password')
            if password:
                user.set_password(password)
            user.save()
            messages.success(request, '個人資料已更新')
            return redirect('profile')
    else:
        form = UserProfileForm(instance=request.user)
    return render(request, 'tracker/profile.html', {'form': form, 'edit_mode': edit_mode})

@login_required
def update_prices(request):
    if request.method == 'POST':
        updated_count = 0
        with connection.cursor() as cursor:
            # 撈出該使用者目前收藏的所有不重複商品
            cursor.execute("""
                SELECT DISTINCT p.id, p.name, p.platform, p.external_id
                FROM user_inventories ui
                JOIN products p ON ui.product_id = p.id
                WHERE ui.user_id = %s
            """, [request.user.id])
            products = cursor.fetchall()
            
            for p_id, p_name, p_platform, p_external_id in products:
                if p_platform == 'PTCG API':
                    ptcg_price = get_ptcg_card_price(p_external_id)
                    if ptcg_price > 0:
                        cursor.execute("""
                            INSERT INTO price_histories (product_id, market_price, platform, recorded_at)
                            VALUES (%s, %s, 'PTCG API', datetime('now'))
                        """, [p_id, ptcg_price])
                        updated_count += 1
                        
                    ebay_price = get_ebay_average_price(p_name)
                    if ebay_price > 0:
                        cursor.execute("""
                            INSERT INTO price_histories (product_id, market_price, platform, recorded_at)
                            VALUES (%s, %s, 'eBay', datetime('now'))
                        """, [p_id, ebay_price])
                        updated_count += 1
                else:
                    # 預設為 eBay 或其他，使用商品名稱搜尋最新平均價
                    ebay_price = get_ebay_average_price(p_name)
                    if ebay_price > 0:
                        cursor.execute("""
                            INSERT INTO price_histories (product_id, market_price, platform, recorded_at)
                            VALUES (%s, %s, 'eBay', datetime('now'))
                        """, [p_id, ebay_price])
                        updated_count += 1
                    
        messages.success(request, f'成功新增了 {updated_count} 筆歷史價格紀錄！')
    return redirect('index')
@login_required
def edit_inventory(request, product_id):
    if request.method == 'GET':
        with connection.cursor() as cursor:
            # 撈出該使用者的特定商品（包含整合後的數量與平均價格）
            sql = """
                SELECT p.name, p.imgurl, p.platform, p.category,
                       SUM(ui.quantity) AS total_quantity,
                       AVG(ui.purchase_price) AS avg_purchase_price
                FROM user_inventories ui
                JOIN products p ON ui.product_id = p.id
                WHERE ui.user_id = %s AND p.id = %s
                GROUP BY p.id, p.name, p.imgurl, p.platform, p.category
            """
            cursor.execute(sql, [request.user.id, product_id])
            row = cursor.fetchone()
            
            if not row:
                messages.error(request, '找不到該商品')
                return redirect('index')
                
            context = {
                'product_id': product_id,
                'name': row[0],
                'image_url': row[1],
                'platform': row[2],
                'category': row[3],
                'quantity': row[4],
                'purchase_price': round(row[5], 2) if row[5] else 0
            }
        return render(request, 'tracker/edit_inventory.html', context)
        
    elif request.method == 'POST':
        action = request.POST.get('action')
        user_id = request.user.id
        
        with connection.cursor() as cursor:
            if action == 'delete':
                cursor.execute("DELETE FROM user_inventories WHERE user_id = %s AND product_id = %s", [user_id, product_id])
                messages.success(request, '已從收藏清單中移除')
            else:
                quantity = request.POST.get('quantity')
                purchase_price = request.POST.get('purchase_price')
                
                # 因為原本設計可能有重複多筆，這裡做 Consolidated Update
                # 先刪除全部舊紀錄，再寫入一筆統整後的新紀錄
                cursor.execute("DELETE FROM user_inventories WHERE user_id = %s AND product_id = %s", [user_id, product_id])
                
                cursor.execute("""
                    INSERT INTO user_inventories (user_id, product_id, purchase_price, purchase_date, quantity)
                    VALUES (%s, %s, %s, date('now'), %s)
                """, [user_id, product_id, purchase_price, quantity])
                
                messages.success(request, '收藏品已更新')
                
        return redirect('index')

def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Automatically log in the user after registration
            login(request, user)
            messages.success(request, 'Registration successful. Welcome to CollectX!')
            return redirect('index')
    else:
        form = UserCreationForm()
    return render(request, 'registration/register.html', {'form': form})
