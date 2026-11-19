from django.urls import path

from . import portal_views as views

app_name = "discipleship"

urlpatterns = [
    path(
        "discipleship/registrations/<int:pk>/step/<slug:step>/",
        views.registration_step,
        name="registration_step",
    ),
    path(
        "discipleship/registrations/<int:pk>/enroll/", views.registration_enroll, name="registration_enroll"
    ),
    path("discipleship/follow-ups/<int:pk>/step/<slug:step>/", views.follow_up_step, name="follow_up_step"),
    path("discipleship/sessions/<int:pk>/attendance/", views.attendance, name="attendance"),
]
