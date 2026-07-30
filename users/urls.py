from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

app_name = 'users'

urlpatterns = [
    path('vhod/', views.enter, name='enter'),
    path('vyhod/', LogoutView.as_view(), name='logout'),
    path('kabinet/', views.profile, name='profile'),
]
