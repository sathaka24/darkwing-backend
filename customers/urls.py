from django.urls import path
from . import views

urlpatterns = [
    path('',          views.CustomerListCreateView.as_view(), name='customer_list_create'), # TODO: 
    path('<int:pk>/', views.CustomerDetailView.as_view(),     name='customer_detail'),      # TODO:
]