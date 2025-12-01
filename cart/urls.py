from django.urls import path
from . import views
app_name='cart'
urlpatterns = [
    path('', views.cart_view, name='cart'),
    path('add/<int:variant_id>/', views.add_to_cart, name='add_to_cart'),
    path('cart/update_quantity/', views.update_cart_quantity, name='update_cart_quantity'),
    path('cart/remove_item/', views.remove_cart_item, name='remove_cart_item'),  
    path('checkout/', views.checkout_view, name='checkout'),  
    path('apply-coupon/', views.apply_coupon, name='apply_coupon'),
    path('set-default-address/<int:address_id>/', views.set_default_address, name='set_default_address'),
    path('place-order/', views.place_order, name='place_order'),
    path('order-success/<int:order_id>/', views.order_success, name='order_success'), 
    path('order/<int:order_id>/', views.order_detail, name='order_detail'),    
        path('order/<int:order_id>/cancel/', views.cancel_order, name='cancel_order'),
    path('order/<int:order_id>/cancel-item/<int:item_id>/', views.cancel_order_item, name='cancel_order_item'),
    path('order/<int:item_id>/return/', views.return_order, name='return_order'),
    path('order/<int:order_id>/invoice/', views.download_invoice, name='order_invoice'),
    path('order/<int:order_id>/', views.order_detail, name='order_detail'),
    #    path('razorpay/payment/', views.razorpay_payment, name='razorpay_payment'),
    path('razorpay/success/', views.razorpay_success, name='razorpay_success'),
        path('remove-coupon/', views.remove_coupon, name='remove_coupon'),
            path('payment-failed/<int:order_id>/', views.payment_failed, name='payment_failed'),
path('retry-payment/<int:order_id>/', views.retry_payment, name='retry_payment'),
path('razorpay-failed/<int:order_id>/', views.razorpay_failed, name='razorpay_failed'),

]
