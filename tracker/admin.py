from django.contrib import admin
from .models import Collectible, UserCollection, Market_Price

admin.site.register(Collectible)
admin.site.register(UserCollection)
admin.site.register(Market_Price)
