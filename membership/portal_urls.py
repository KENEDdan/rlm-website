from django.urls import path

from . import portal_views as views

app_name = "membership"

urlpatterns = [
    path("membership/members/<int:pk>/step/<slug:name>/", views.member_step, name="member_step"),
    path("membership/activities/<int:pk>/attendance/", views.attendance, name="attendance"),
    path("membership/messages/<int:pk>/send/", views.send, name="send"),
    path("membership/messages/<int:pk>/whatsapp/", views.whatsapp, name="whatsapp"),
]
