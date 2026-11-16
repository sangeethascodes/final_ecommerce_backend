from app import views
from django.urls import path
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)


urlpatterns=[
    path('',views.getRoutes,name="getRoutes"),
    path('products/',views.getProducts,name="getProducts"),
    path('product/<str:pk>',views.getProduct,name="getProduct"),
    path('users/login',views.MyTokenObtainPairView.as_view(),name='token_obtain_pair'),
    path('users/register',views.registerUser,name='register'),
    path('users/profile/',views.updateUserProfile,name='user-profile'),
    path('activate/<uidb64>/<token>',views.ActivateAccountView.as_view(),name='activate'),
    path('orders/add/',views.addOrderItems,name='orders-add'),
    path('orders/',views.getOrders,name='orders'),
    path('orders/myorders/',views.getMyOrders,name='myorders'),
    path('orders/<str:pk>/',views.getOrderById,name='user-order'),
    
    #admin urls
    path('products/create/',views.createProduct,name='product-create'),
    path('products/update/<str:pk>/',views.updateProduct,name='product-create'),
    path('products/delete/<str:pk>/',views.deleteProduct,name='product-delete'),
    path('products/upload/',views.uploadImage,name='image-upload'),
    path('users/getallusers/',views.getUsers,name='users')
    # path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    
    
    
]
