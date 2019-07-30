from django.urls import path
from . import views

urlpatterns = [
    path('', views.HomeView.as_view(), name='home'),
    path('add_post', views.AddPostView.as_view(), name='add_post'),
    path('search_wizard', views.SearchWizardView.as_view(), name='search_wizard'),
    path('my_posts', views.MyPostsListView.as_view(), name='my_posts'),
    path('post_detail/<int:id>/', views.PostDetailView.as_view(), name='post_detail'),
]

