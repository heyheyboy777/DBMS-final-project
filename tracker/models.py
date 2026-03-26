from django.db import models
from django.contrib.auth.models import User

# 收藏品目錄 (Product Master)
class Product(models.Model):
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=50) # 如：卡牌、球鞋
    external_id = models.CharField(max_length=100, unique=True)
    
    class Meta:
        db_table = 'products' # 讓 Raw SQL 更好寫

# 個人庫存 (User Inventory)
class UserInventory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2)
    purchase_date = models.DateField()
    quantity = models.IntegerField(default=1)

    class Meta:
        db_table = 'user_inventories'

# 行情歷史 (Price History)
class PriceHistory(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    market_price = models.DecimalField(max_digits=10, decimal_places=2)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'price_histories'
# Create your models here.
