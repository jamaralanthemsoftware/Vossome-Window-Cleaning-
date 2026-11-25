from django.urls import path

from .views import capabilities, media, page_detail, pages, site_revision

app_name = "anthem_seo"

urlpatterns = [
    path("capabilities/", capabilities, name="capabilities"),
    path("site/", capabilities, name="site"),
    path("revision/", site_revision, name="revision"),
    path("pages/", pages, name="pages"),
    path("pages/<str:item_id>/", page_detail, name="page-detail"),
    path("media/", media, name="media"),
]
