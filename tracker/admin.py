from django.contrib import admin
from .models import Product, UserInventory, PriceHistory

admin.site.register(Product)
admin.site.register(UserInventory)
admin.site.register(PriceHistory)
# Register your models here.
