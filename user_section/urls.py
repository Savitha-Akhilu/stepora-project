from django.urls import path,include
from . import views

urlpatterns = [
    path('signup/', views.signup, name='signup'),
    path('verify-otp/', views.verify_otp, name='verify_otp'),
    path('resend-otp/', views.resend_otp, name='resend_otp'),
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),
    path('', views.user_home, name='user_home'),
    path('login/redirect/', views.redirect_after_login, name='redirect_after_login'),
    path('check-email/', views.check_email_exists, name='check_email'),
    path('check-phone/', views.check_phone, name='check_phone'),
    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path('verify-reset-otp/', views.verify_reset_otp, name='verify_reset_otp'),
    path('reset-password/', views.reset_password, name='reset_password'),
    path('men/', views.men_collections, name='men_collection'),
    path('women/', views.women_collection, name='women_collection'),
    path('product/<int:product_id>/', views.product_detail, name='product_detail'),
        path('profile/', views.user_profile, name='user_profile'),
    path('address/', views.manage_address, name='user_address'),
    path('address/add/', views.add_address, name='add_address'),
    path('address/edit/<int:id>/', views.edit_address, name='edit_address'),
    path('address/delete/<int:pk>/', views.delete_address, name='delete_address'),
    path('update-profile-image/', views.update_profile_image, name='update_profile_image'), 
    path('update-profile-info/', views.update_profile_info, name='update_profile_info'),
    path('send-email-otp/', views.send_email_otp, name='send_email_otp'),
    path('verify-email-otp/', views.verify_email_otp, name='verify_email_otp'),
    path('change-password/', views.change_password, name='change_password'),
    path('cart/', include('cart.urls')),
    path('my-orders/', views.my_orders, name='my_orders'),

    path('wishlist/', views.wishlist, name='wishlist'),
    # path('wishlist/add/<int:variant_id>/', views.add_to_wishlist, name='add_to_wishlist'),
    path('wishlist/add/<int:variant_id>/', views.add_to_wishlist, name='add_to_wishlist'),
    path('wishlist/remove/<int:item_id>/', views.remove_from_wishlist, name='remove_from_wishlist'),
    path('wishlist/move-all/', views.move_all_to_cart, name='move_all_to_cart'),
    path('wishlist/clear/', views.clear_wishlist, name='clear_wishlist'),
    path('validate-referral/', views.validate_referral, name='validate_referral'),
            path('search/', views.search_products, name='search_products'),
                path('wallet/', views.my_wallet, name='my_wallet'),
                path('refer/', views.refer_and_earn, name='refer_and_earn'),

path("address/get/<int:id>/", views.get_address, name="get_address"),

path("about/", views.about_page, name="about"),
path("customer-care/", views.customer_care, name="customer_care"),
path("contact/", views.contact_page, name="contact"),
path("privacy-policy/", views.privacy_policy, name="privacy_policy"),
path("shipping-returns/", views.shipping_returns, name="shipping_returns"),


]
