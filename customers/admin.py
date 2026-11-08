from django.contrib import admin

from .models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("customer_code", "name", "mobile", "email", "created_at")
    search_fields = ("customer_code", "name", "mobile")
    readonly_fields = ("customer_code", "created_at", "updated_at")
    ordering = ("name",)