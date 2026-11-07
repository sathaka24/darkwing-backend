from django.urls import path
from . import views

urlpatterns = [
    path('',                        views.InvoiceListCreateView.as_view(), name='invoice_list_create'), # TODO:
    path('<int:pk>/',               views.InvoiceDetailView.as_view(),     name='invoice_detail'),      # TODO:
    path('<int:pk>/payments/',      views.PaymentCreateView.as_view(),     name='invoice_payment'),     # TODO:
    path('<int:pk>/mark-paid/',     views.InvoiceMarkPaidView.as_view(),   name='invoice_mark_paid'),   # TODO:
    path('<int:pk>/cancel/',        views.InvoiceCancelView.as_view(),     name='invoice_cancel'),      # TODO:
]