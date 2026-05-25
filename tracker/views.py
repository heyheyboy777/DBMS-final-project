import json
from django.shortcuts import render, redirect
from django.db import connection
from .services import search_ebay_items, search_ptcg_cards, get_ptcg_card_price, get_ebay_average_price, fetch_ptcg_news
from django.contrib.auth.decorators import login_required
from datetime import date
import datetime
from .forms import UserProfileForm
from django.contrib import messages
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login

# Create your views here.
def index(request):
    """Dashboard — overview of portfolio with summary stats."""
    context = {
        'total_items': 0,
        'total_investment': 0,
        'current_value': 0,
        'total_pl': 0,
        'total_pl_pct': 0,
        'category_breakdown': [],
        'recent_changes': [],
        'top_gainers': [],
        'top_losers': [],
    }

    if request.user.is_authenticated:
        with connection.cursor() as cursor:
            # ── 1. Portfolio Summary ──
            cursor.execute("""
                SELECT 
                    COUNT(DISTINCT p.id) AS total_items,
                    SUM(ui.purchase_price * ui.quantity) AS total_investment,
                    SUM(ui.quantity) AS total_qty
                FROM user_inventories ui
                JOIN products p ON ui.product_id = p.id
                WHERE ui.user_id = %s
            """, [request.user.id])
            summary = cursor.fetchone()
            total_items = summary[0] or 0
            total_investment = float(summary[1]) if summary[1] else 0

            # ── 2. Current Value (latest price × quantity) ──
            cursor.execute("""
                SELECT 
                    p.id, p.name, p.category, p.imgurl,
                    SUM(ui.quantity) AS qty,
                    AVG(ui.purchase_price) AS avg_buy,
                    (SELECT ph.market_price FROM price_histories ph 
                     WHERE ph.product_id = p.id 
                     ORDER BY ph.recorded_at DESC LIMIT 1) AS latest_price,
                    (SELECT ph.market_price FROM price_histories ph 
                     WHERE ph.product_id = p.id 
                       AND DATE(ph.recorded_at) <= DATE('now', '-1 day')
                     ORDER BY ph.recorded_at DESC LIMIT 1) AS yesterday_price
                FROM user_inventories ui
                JOIN products p ON ui.product_id = p.id
                WHERE ui.user_id = %s
                GROUP BY p.id, p.name, p.category, p.imgurl
            """, [request.user.id])
            rows = cursor.fetchall()

            current_value = 0
            category_totals = {}
            changes = []

            for row in rows:
                pid, name, category, imgurl = row[0], row[1], row[2] or 'Other', row[3]
                qty = int(row[4])
                avg_buy = float(row[5]) if row[5] else 0
                latest = float(row[6]) if row[6] else avg_buy
                yesterday = float(row[7]) if row[7] else latest

                item_value = latest * qty
                current_value += item_value

                # Category breakdown
                if category not in category_totals:
                    category_totals[category] = 0
                category_totals[category] += item_value

                # Daily change
                daily_change = ((latest - yesterday) / yesterday * 100) if yesterday else 0
                pl = (latest - avg_buy) * qty
                pl_pct = ((latest - avg_buy) / avg_buy * 100) if avg_buy else 0

                changes.append({
                    'name': name,
                    'category': category,
                    'imgurl': imgurl,
                    'latest_price': round(latest, 2),
                    'daily_change': round(daily_change, 2),
                    'pl': round(pl, 2),
                    'pl_pct': round(pl_pct, 2),
                    'qty': qty,
                })

            total_pl = current_value - total_investment
            total_pl_pct = (total_pl / total_investment * 100) if total_investment else 0

            # Category breakdown for donut
            category_breakdown = [{'category': k, 'value': round(v, 2)} 
                                  for k, v in sorted(category_totals.items(), key=lambda x: -x[1])]

            # Top gainers / losers
            sorted_by_daily = sorted(changes, key=lambda x: x['daily_change'], reverse=True)
            top_gainers = [c for c in sorted_by_daily if c['daily_change'] > 0][:3]
            top_losers = [c for c in sorted_by_daily if c['daily_change'] < 0][-3:][::-1]
            # Reverse losers so worst is first
            top_losers = sorted(top_losers, key=lambda x: x['daily_change'])

            context.update({
                'total_items': total_items,
                'total_investment': round(total_investment, 2),
                'current_value': round(current_value, 2),
                'total_pl': round(total_pl, 2),
                'total_pl_pct': round(total_pl_pct, 2),
                'category_breakdown': json.dumps(category_breakdown),
                'recent_changes': changes,
                'top_gainers': top_gainers,
                'top_losers': top_losers,
            })

    return render(request, 'tracker/dashboard.html', context)


@login_required
def inventory_view(request):
    """Inventory page — detailed listing of all user's items."""
    inventory_list = []

    with connection.cursor() as cursor:
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
            messages.success(request, 'Registration successful. Welcome to Collect Terminal!')
            return redirect('index')
    else:
        form = UserCreationForm()
    return render(request, 'registration/register.html', {'form': form})

@login_required
def roi_dashboard(request):
    with connection.cursor() as cursor:
        sql = """
            SELECT p.id, p.name, p.imgurl, p.category, p.platform,
                   SUM(ui.quantity) AS total_quantity,
                   AVG(ui.purchase_price) AS avg_purchase_price,
                   
                   (SELECT market_price FROM price_histories 
                    WHERE product_id = p.id AND platform = 'PTCG API' 
                    ORDER BY recorded_at DESC LIMIT 1) AS ptcg_price,
                    
                   (SELECT market_price FROM price_histories 
                    WHERE product_id = p.id AND platform = 'eBay' 
                    ORDER BY recorded_at DESC LIMIT 1) AS ebay_price
            FROM user_inventories ui
            JOIN products p ON ui.product_id = p.id
            WHERE ui.user_id = %s
            GROUP BY p.id, p.name, p.imgurl, p.category, p.platform
        """
        cursor.execute(sql, [request.user.id])
        rows = cursor.fetchall()
        
        category_totals = {}
        total_cost = 0
        total_value = 0
        item_roi_list = []
        
        for row in rows:
            product_id = row[0]
            name = row[1]
            image = row[2]
            category = row[3]
            platform = row[4]
            quantity = row[5]
            avg_purchase = row[6]
            ptcg_price = row[7]
            ebay_price = row[8]
            
            # Determine current price
            current_price = avg_purchase
            if platform == 'PTCG API' and ptcg_price is not None:
                current_price = ptcg_price
            elif platform == 'eBay' and ebay_price is not None:
                current_price = ebay_price
                
            # Calculate metrics
            item_cost = float(avg_purchase) * quantity
            item_value = float(current_price) * quantity
            item_profit = item_value - item_cost
            item_roi_percent = (item_profit / item_cost * 100) if item_cost > 0 else 0
            
            cat_name = category if category else "Other"
            if cat_name not in category_totals:
                category_totals[cat_name] = 0
            category_totals[cat_name] += item_value
            
            total_cost += item_cost
            total_value += item_value
            
            item_roi_list.append({
                'name': name,
                'image': image,
                'category': cat_name,
                'quantity': quantity,
                'cost': round(item_cost, 2),
                'value': round(item_value, 2),
                'profit': round(item_profit, 2),
                'roi_percent': round(item_roi_percent, 2)
            })
            
        item_roi_list.sort(key=lambda x: x['roi_percent'], reverse=True)
        total_profit = total_value - total_cost
        
        category_labels = list(category_totals.keys())
        category_values = [round(val, 2) for val in category_totals.values()]
        
        context = {
            'category_labels': json.dumps(category_labels),
            'category_values': json.dumps(category_values),
            'total_cost': round(total_cost, 2),
            'total_value': round(total_value, 2),
            'total_profit': round(total_profit, 2),
            'item_roi_list': item_roi_list
        }
        
    return render(request, 'tracker/roi.html', context)

@login_required
def analytics_dashboard(request):
    import math

    with connection.cursor() as cursor:
        # 1. Fetch user's inventory
        sql_inv = """
            SELECT p.id, p.name, p.category, 
                   SUM(ui.quantity) AS total_quantity,
                   AVG(ui.purchase_price) AS avg_purchase_price
            FROM user_inventories ui
            JOIN products p ON ui.product_id = p.id
            WHERE ui.user_id = %s
            GROUP BY p.id, p.name, p.category
        """
        cursor.execute(sql_inv, [request.user.id])
        inventory_rows = cursor.fetchall()
        
        products = {}
        for row in inventory_rows:
            pid = row[0]
            products[pid] = {
                'id': pid,
                'name': row[1],
                'category': row[2] if row[2] else "Other",
                'qty': row[3],
                'base_price': float(row[4]),
                'histories': {}
            }
        
        if not products:
            return render(request, 'tracker/analytics.html', {'error': 'No inventory to analyze.'})
            
        pids = list(products.keys())
        placeholders = ', '.join(['%s'] * len(pids))
        
        # 2. Fetch price histories (include [SEED] data)
        sql_hist = f"""
            SELECT product_id, market_price, DATE(recorded_at) as rec_date
            FROM price_histories
            WHERE product_id IN ({placeholders})
            ORDER BY recorded_at ASC
        """
        cursor.execute(sql_hist, pids)
        hist_rows = cursor.fetchall()
        
        all_dates = set()
        
        for row in hist_rows:
            pid = row[0]
            price = float(row[1])
            date_str = row[2]
            products[pid]['histories'][date_str] = price
            all_dates.add(date_str)
            
        today_str = datetime.date.today().strftime('%Y-%m-%d')
        all_dates.add(today_str)
        
        sorted_dates = sorted(list(all_dates))
        
        if not sorted_dates:
            sorted_dates = [today_str]
            
        # 3. Build time-series
        timeline_labels = sorted_dates
        overall_net_worth = []
        category_net_worth = {}
        individual_trends = {}
        
        categories = set(p['category'] for p in products.values())
        for cat in categories:
            category_net_worth[cat] = []
            
        for d in sorted_dates:
            day_total = 0
            day_cat_totals = {cat: 0 for cat in categories}
            
            for pid, p in products.items():
                past_dates = [hd for hd in p['histories'].keys() if hd <= d]
                if past_dates:
                    latest_date = max(past_dates)
                    current_price = p['histories'][latest_date]
                else:
                    current_price = p['base_price']
                    
                item_value = current_price * p['qty']
                day_total += item_value
                day_cat_totals[p['category']] += item_value
                
                if pid not in individual_trends:
                    individual_trends[pid] = {'name': p['name'], 'data': []}
                individual_trends[pid]['data'].append(round(current_price, 2))
                
            overall_net_worth.append(round(day_total, 2))
            for cat in categories:
                category_net_worth[cat].append(round(day_cat_totals[cat], 2))

        # ──────────────────────────────────────────────
        # 4. Calculate Professional Portfolio Metrics
        # ──────────────────────────────────────────────
        
        # Total cost basis
        total_cost = sum(p['base_price'] * p['qty'] for p in products.values())
        
        # Daily returns (percentage)
        daily_returns = []
        for i in range(1, len(overall_net_worth)):
            if overall_net_worth[i - 1] != 0:
                ret = (overall_net_worth[i] - overall_net_worth[i - 1]) / overall_net_worth[i - 1]
                daily_returns.append(ret)
        
        # Total Return
        initial_value = overall_net_worth[0] if overall_net_worth else 0
        final_value = overall_net_worth[-1] if overall_net_worth else 0
        total_return_pct = ((final_value - initial_value) / initial_value * 100) if initial_value else 0
        
        # Annualized Return
        num_days = len(sorted_dates)
        if num_days > 1 and initial_value > 0:
            annualized_return = ((final_value / initial_value) ** (365.0 / num_days) - 1) * 100
        else:
            annualized_return = 0
            
        # Volatility (annualized)
        if len(daily_returns) > 1:
            mean_ret = sum(daily_returns) / len(daily_returns)
            variance = sum((r - mean_ret) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
            daily_vol = math.sqrt(variance)
            annual_vol = daily_vol * math.sqrt(252) * 100  # percentage
        else:
            daily_vol = 0
            annual_vol = 0
            
        # Sharpe Ratio (risk-free rate = 2% annualized)
        risk_free_rate = 0.02
        if annual_vol > 0:
            sharpe_ratio = (annualized_return / 100 - risk_free_rate) / (annual_vol / 100)
        else:
            sharpe_ratio = 0
            
        # Sortino Ratio (only downside volatility)
        downside_returns = [r for r in daily_returns if r < 0]
        if len(downside_returns) > 1:
            downside_variance = sum(r ** 2 for r in downside_returns) / len(downside_returns)
            downside_vol = math.sqrt(downside_variance) * math.sqrt(252)
            sortino_ratio = (annualized_return / 100 - risk_free_rate) / downside_vol if downside_vol > 0 else 0
        else:
            sortino_ratio = 0

        # Maximum Drawdown
        peak = overall_net_worth[0] if overall_net_worth else 0
        max_drawdown = 0
        drawdown_series = []
        for val in overall_net_worth:
            if val > peak:
                peak = val
            dd = (val - peak) / peak * 100 if peak > 0 else 0
            drawdown_series.append(round(dd, 2))
            if dd < max_drawdown:
                max_drawdown = dd
                
        # Calmar Ratio = Annualized Return / |Max Drawdown|
        calmar_ratio = (annualized_return / abs(max_drawdown)) if max_drawdown != 0 else 0
        
        # Win Rate
        positive_days = sum(1 for r in daily_returns if r > 0)
        win_rate = (positive_days / len(daily_returns) * 100) if daily_returns else 0
        
        # Best / Worst day
        best_day = max(daily_returns) * 100 if daily_returns else 0
        worst_day = min(daily_returns) * 100 if daily_returns else 0
        
        # Daily returns as percentage for chart (capped for display)
        daily_returns_pct = [round(r * 100, 2) for r in daily_returns]
        daily_returns_labels = timeline_labels[1:] if len(timeline_labels) > 1 else timeline_labels
        
        # Moving averages for overall net worth
        def moving_average(data, window):
            ma = []
            for i in range(len(data)):
                if i < window - 1:
                    ma.append(None)
                else:
                    avg = sum(data[i - window + 1:i + 1]) / window
                    ma.append(round(avg, 2))
            return ma
        
        ma7 = moving_average(overall_net_worth, 7)
        ma30 = moving_average(overall_net_worth, 30)
        
        # Category allocation (latest values)
        category_allocation = {}
        if category_net_worth:
            for cat, values in category_net_worth.items():
                if values:
                    category_allocation[cat] = values[-1]

        # Build metrics dict
        portfolio_metrics = {
            'total_return': round(total_return_pct, 2),
            'annualized_return': round(annualized_return, 2),
            'max_drawdown': round(max_drawdown, 2),
            'sharpe_ratio': round(sharpe_ratio, 2),
            'sortino_ratio': round(sortino_ratio, 2),
            'calmar_ratio': round(calmar_ratio, 2),
            'win_rate': round(win_rate, 1),
            'volatility': round(annual_vol, 2),
            'best_day': round(best_day, 2),
            'worst_day': round(worst_day, 2),
            'total_cost': round(total_cost, 2),
            'current_value': round(final_value, 2),
            'total_profit': round(final_value - total_cost, 2),
        }
                
        context = {
            'timeline_labels': json.dumps(timeline_labels),
            'overall_net_worth': json.dumps(overall_net_worth),
            'category_net_worth': json.dumps(category_net_worth),
            'individual_trends': json.dumps(individual_trends),
            'products_list': [{'id': p['id'], 'name': p['name']} for p in products.values()],
            # New data for professional charts
            'drawdown_series': json.dumps(drawdown_series),
            'daily_returns_pct': json.dumps(daily_returns_pct),
            'daily_returns_labels': json.dumps(daily_returns_labels),
            'ma7': json.dumps(ma7),
            'ma30': json.dumps(ma30),
            'portfolio_metrics': json.dumps(portfolio_metrics),
            'category_allocation': json.dumps(category_allocation),
            'metrics': portfolio_metrics,
        }
        
    return render(request, 'tracker/analytics.html', context)


@login_required
def market_dashboard(request):
    with connection.cursor() as cursor:
        today = datetime.date.today()
        seven_days_ago = (today - datetime.timedelta(days=7)).strftime('%Y-%m-%d')
        thirty_days_ago = (today - datetime.timedelta(days=30)).strftime('%Y-%m-%d')
        today_str = today.strftime('%Y-%m-%d')

        # ──────────────────────────────────────
        # 1. Hot Assets Ranking
        # ──────────────────────────────────────
        # Get all products with their latest price, 7d-ago price, 30d-ago price
        cursor.execute("""
            SELECT p.id, p.name, p.category, p.platform, p.imgurl,
                   -- Latest price
                   (SELECT ph.market_price FROM price_histories ph
                    WHERE ph.product_id = p.id
                    ORDER BY ph.recorded_at DESC LIMIT 1) AS latest_price,
                   -- Price ~7 days ago
                   (SELECT ph.market_price FROM price_histories ph
                    WHERE ph.product_id = p.id AND DATE(ph.recorded_at) <= %s
                    ORDER BY ph.recorded_at DESC LIMIT 1) AS price_7d,
                   -- Price ~30 days ago
                   (SELECT ph.market_price FROM price_histories ph
                    WHERE ph.product_id = p.id AND DATE(ph.recorded_at) <= %s
                    ORDER BY ph.recorded_at DESC LIMIT 1) AS price_30d
            FROM products p
            WHERE EXISTS (SELECT 1 FROM price_histories ph2 WHERE ph2.product_id = p.id)
            ORDER BY p.id
        """, [seven_days_ago, thirty_days_ago])
        product_rows = cursor.fetchall()

        # Build sparkline data (last 7 days prices for each product)
        ranking_list = []
        product_ids_for_sparkline = []

        for row in product_rows:
            pid = row[0]
            name = row[1]
            category = row[2] or 'Other'
            platform = row[3]
            imgurl = row[4]
            latest_price = float(row[5]) if row[5] else 0
            price_7d = float(row[6]) if row[6] else latest_price
            price_30d = float(row[7]) if row[7] else latest_price

            change_7d = ((latest_price - price_7d) / price_7d * 100) if price_7d else 0
            change_30d = ((latest_price - price_30d) / price_30d * 100) if price_30d else 0

            ranking_list.append({
                'id': pid,
                'name': name,
                'category': category,
                'platform': platform,
                'imgurl': imgurl,
                'latest_price': round(latest_price, 2),
                'change_7d': round(change_7d, 2),
                'change_30d': round(change_30d, 2),
            })
            product_ids_for_sparkline.append(pid)

        # Sort by 7d change descending
        ranking_list.sort(key=lambda x: x['change_7d'], reverse=True)

        # Fetch sparkline data (last 7 daily prices per product)
        sparkline_data = {}
        if product_ids_for_sparkline:
            placeholders = ', '.join(['%s'] * len(product_ids_for_sparkline))
            cursor.execute(f"""
                SELECT product_id, market_price, DATE(recorded_at) as d
                FROM price_histories
                WHERE product_id IN ({placeholders})
                  AND DATE(recorded_at) >= %s
                ORDER BY recorded_at ASC
            """, product_ids_for_sparkline + [seven_days_ago])
            spark_rows = cursor.fetchall()

            for sr in spark_rows:
                pid = sr[0]
                price = float(sr[1])
                if pid not in sparkline_data:
                    sparkline_data[pid] = []
                sparkline_data[pid].append(price)

        # Attach sparkline to ranking
        for item in ranking_list:
            item['sparkline'] = sparkline_data.get(item['id'], [])

        # ──────────────────────────────────────
        # 2. Category Heatmap
        # ──────────────────────────────────────
        category_map = {}
        for item in ranking_list:
            cat = item['category']
            if cat not in category_map:
                category_map[cat] = {
                    'category': cat,
                    'total_value': 0,
                    'changes_7d': [],
                    'count': 0
                }
            category_map[cat]['total_value'] += item['latest_price']
            category_map[cat]['changes_7d'].append(item['change_7d'])
            category_map[cat]['count'] += 1

        heatmap_data = []
        for cat, data in category_map.items():
            avg_change = sum(data['changes_7d']) / len(data['changes_7d']) if data['changes_7d'] else 0
            heatmap_data.append({
                'category': cat,
                'value': round(data['total_value'], 2),
                'change': round(avg_change, 2),
                'count': data['count']
            })

        # Sort by value descending for treemap layout
        heatmap_data.sort(key=lambda x: x['value'], reverse=True)

    # ──────────────────────────────────────
    # 3. PTCG News
    # ──────────────────────────────────────
    news_list = fetch_ptcg_news()

    context = {
        'ranking_list': ranking_list,
        'heatmap_data': json.dumps(heatmap_data),
        'news_list': news_list,
        'sparkline_json': json.dumps({str(k): v for k, v in sparkline_data.items()}),
    }

    return render(request, 'tracker/market.html', context)


@login_required
def refresh_news(request):
    """AJAX endpoint to refresh PTCG news without page reload."""
    from django.http import JsonResponse
    if request.method == 'POST':
        news_list = fetch_ptcg_news()
        return JsonResponse({'news': news_list})
    return JsonResponse({'error': 'POST required'}, status=405)
