from django.urls import path
from . import views

urlpatterns = [

    path('login/',   views.LoginView.as_view(),   name='login'),
    path('refresh/', views.RefreshView.as_view(),  name='refresh'),
]

# in above url patterns we use as_view(). it hands Django a reqular function wrapper. cuz Django expect a regular function that accept request in Path()
# since that wrapper given to Django it create a instance like view = LoginView(). then it calls view.dispatch(request) here it checks which type 
# request has came like POST, GET,... then it passes the request to correct function. that's why inside the class there are functions called
# post(), get() likewise are there