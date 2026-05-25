"""
seed_price_data — 為所有現有產品回填 6 個月的模擬每日價格數據。

使用 Geometric Brownian Motion (GBM) 產生真實感的價格走勢：
  dS = S * (μ*dt + σ*dW)

不同類型的收藏品設有不同的漂移率 (drift) 和波動率 (volatility)，
以模擬各品類的真實市場行為。
"""

import math
import random
import datetime
from django.core.management.base import BaseCommand
from django.db import connection


# 各品類的參數配置：(年化漂移率, 年化波動率)
# drift > 0 表示長期上漲趨勢
CATEGORY_PARAMS = {
    'Pokémon Cards':        (0.15, 0.45),   # 高波動、緩慢上漲
    'Other':                (0.05, 0.30),   # 一般收藏品
    'LEGO (R) Complete Sets': (0.08, 0.15), # LEGO 較穩定
    'Video Game Consoles':  (-0.10, 0.20),  # 電子產品會折舊
    'Montblanc':            (0.03, 0.12),   # 精品較穩
}

DEFAULT_PARAMS = (0.05, 0.30)
SEED_DAYS = 180  # 6 個月


class Command(BaseCommand):
    help = '為所有產品回填 6 個月的模擬每日價格歷史數據'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days', type=int, default=SEED_DAYS,
            help='回填的天數 (預設: 180)'
        )
        parser.add_argument(
            '--clear', action='store_true',
            help='執行前先清除所有 seed 產生的假資料 (帶有 [SEED] 標記)'
        )

    def handle(self, *args, **options):
        days = options['days']
        clear = options['clear']

        with connection.cursor() as cursor:
            if clear:
                # 刪除先前 seed 的資料（以 platform 包含 [SEED] 標記辨識）
                cursor.execute(
                    "DELETE FROM price_histories WHERE platform LIKE '%[SEED]%'"
                )
                self.stdout.write(self.style.WARNING('已清除先前的假資料'))

            # 取得所有產品
            cursor.execute(
                "SELECT id, name, category, platform FROM products"
            )
            products = cursor.fetchall()

            if not products:
                self.stdout.write(self.style.ERROR('沒有產品資料，請先加入收藏品'))
                return

            total_inserted = 0
            today = datetime.date.today()
            start_date = today - datetime.timedelta(days=days)

            for prod_id, name, category, platform in products:
                # 取得該產品最早的真實價格作為基準
                cursor.execute(
                    """SELECT market_price FROM price_histories
                       WHERE product_id = %s AND platform NOT LIKE '%%[SEED]%%'
                       ORDER BY recorded_at ASC LIMIT 1""",
                    [prod_id]
                )
                row = cursor.fetchone()
                if row:
                    base_price = float(row[0])
                else:
                    # 沒有歷史價格，嘗試從 user_inventories 拿 purchase_price
                    cursor.execute(
                        """SELECT purchase_price FROM user_inventories
                           WHERE product_id = %s LIMIT 1""",
                        [prod_id]
                    )
                    inv_row = cursor.fetchone()
                    if inv_row:
                        base_price = float(inv_row[0])
                    else:
                        base_price = 100.0  # fallback

                # 選擇對應品類的參數
                mu, sigma = CATEGORY_PARAMS.get(category, DEFAULT_PARAMS)

                # GBM 模擬
                dt = 1.0 / 252  # 每交易日
                prices = self._simulate_gbm(base_price, mu, sigma, dt, days)

                # 寫入 price_histories
                seed_platform = f"{platform} [SEED]"
                for i, price in enumerate(prices):
                    record_date = start_date + datetime.timedelta(days=i)
                    record_dt = datetime.datetime.combine(
                        record_date,
                        datetime.time(12, 0, 0)  # 中午 12:00
                    )
                    cursor.execute(
                        """INSERT INTO price_histories
                           (product_id, market_price, platform, recorded_at)
                           VALUES (%s, %s, %s, %s)""",
                        [prod_id, round(price, 2), seed_platform, record_dt]
                    )
                    total_inserted += 1

                self.stdout.write(
                    f'  ✓ {name[:40]:40s} | base=${base_price:>8.2f} | '
                    f'{days} days | final=${prices[-1]:>8.2f}'
                )

            self.stdout.write(self.style.SUCCESS(
                f'\n完成！共插入 {total_inserted} 筆模擬價格數據。'
            ))

    @staticmethod
    def _simulate_gbm(s0, mu, sigma, dt, steps):
        """
        Geometric Brownian Motion 模擬器。
        
        回傳 `steps` 個價格數據的 list（包含起始價 s0 的後續走勢）。
        加入均值回歸力道，避免價格漂移過遠。
        """
        prices = []
        s = s0
        
        # 加入一些隨機 regime changes 增加趣味性
        regime_change_points = sorted(
            random.sample(range(steps), min(3, steps))
        )
        current_regime = 0
        regime_drift_modifiers = [
            random.uniform(-0.3, 0.3) for _ in range(4)
        ]

        for i in range(steps):
            # Regime switching
            if current_regime < len(regime_change_points) and i >= regime_change_points[current_regime]:
                current_regime += 1

            drift_mod = regime_drift_modifiers[min(current_regime, len(regime_drift_modifiers) - 1)]
            effective_mu = mu + drift_mod

            # 均值回歸 — 當價格偏離基準太遠時拉回
            deviation = (s - s0) / s0
            mean_reversion = -0.5 * deviation  # 回歸力道

            # GBM step with mean reversion
            dW = random.gauss(0, math.sqrt(dt))
            ds = s * ((effective_mu + mean_reversion) * dt + sigma * dW)
            s = max(s + ds, s0 * 0.2)  # 最低不低於基準價的 20%

            prices.append(s)

        return prices
