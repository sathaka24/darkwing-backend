from django.contrib import admin

from .models import Invoice, InvoiceItem, Payment, InvoiceCounter


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0
    readonly_fields = ("line_total",)


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "invoice_number", "customer", "status",
        "grand_total", "issue_date", "created_by",
    )
    list_filter = ("status", "warranty_stamp", "issue_date")
    search_fields = (
        "invoice_number", "customer__name", "customer__customer_code",
    )
    readonly_fields = (
        "invoice_number", "grand_total",
        "created_at", "updated_at", "cancelled_at",
    )
    inlines = [InvoiceItemInline, PaymentInline]
    date_hierarchy = "issue_date"


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("invoice", "kind", "amount", "paid_at", "recorded_by")
    list_filter = ("kind", "paid_at")
    search_fields = ("invoice__invoice_number",)


@admin.register(InvoiceCounter)
class InvoiceCounterAdmin(admin.ModelAdmin):
    list_display = ("year", "last_no")
    readonly_fields = ("year", "last_no")