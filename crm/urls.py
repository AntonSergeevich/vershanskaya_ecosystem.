from django.urls import path

from . import views

app_name = 'crm'

urlpatterns = [
    path('', views.board, name='board'),
    path('analitika/', views.analytics, name='analytics'),
    path('lid/<int:pk>/', views.lead_detail, name='lead'),
    path('lid/<int:pk>/perenesti/', views.move_lead, name='move_lead'),
]
