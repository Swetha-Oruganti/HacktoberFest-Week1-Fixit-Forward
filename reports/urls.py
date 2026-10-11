from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("api/analyze/", views.analyze, name="analyze"),
    path("api/reports/", views.create_report, name="create_report"),
    path("api/reports/list/", views.list_reports, name="list_reports"),
    path("api/reports/<str:report_id>/status/", views.update_status, name="update_status"),
    path("api/reports/<str:report_id>/", views.report_detail, name="report_detail"),
    path("health/", views.health, name="health"),
]
