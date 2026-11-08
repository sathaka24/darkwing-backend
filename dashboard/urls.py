from django.urls import path
from . import views

urlpatterns = [
    path('stats/',          views.DashboardStatsView.as_view(), name='dashboard_stats'),  
    path('monthly-report/', views.MonthlyReportView.as_view(),  name='monthly_report'),   
]