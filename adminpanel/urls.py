from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.admin_register, name='admin_register'),
    path('login/', views.admin_login, name='admin_login'),
    path('logout/', views.admin_logout, name='admin_logout'),
    path('dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('users/', views.admin_users, name='admin_users'),
    path('users/admin_toggle_user_status/<int:user_id>/', views.admin_toggle_user_status, name='admin_toggle_block'),
     path('categories/', views.admin_categories, name='admin_categories'),
    path('categories/add/', views.admin_category_add, name='admin_category_add'),
    path('categories/<int:pk>/edit/', views.admin_category_edit, name='admin_category_edit'),
    path('categories/<int:pk>/delete/', views.admin_category_delete, name='admin_category_delete'),
    # Color Management
    path('colors/', views.admin_colors, name='admin_colors'),
    path('colors/add/', views.admin_color_add, name='admin_color_add'),
    path('colors/<int:pk>/edit/', views.admin_color_edit, name='admin_color_edit'),
    path('colors/<int:pk>/delete/', views.admin_color_delete, name='admin_color_delete'),

    # Size Management
    path('sizes/', views.admin_sizes, name='admin_sizes'),
    path('sizes/add/', views.admin_size_add, name='admin_size_add'),
    path('sizes/<int:pk>/edit/', views.admin_size_edit, name='admin_size_edit'),
    path('sizes/<int:pk>/delete/', views.admin_size_delete, name='admin_size_delete'),

    # Material Management
    path('materials/', views.admin_materials, name='admin_materials'),
    path('materials/add/', views.admin_material_add, name='admin_material_add'),
    path('materials/<int:pk>/edit/', views.admin_material_edit, name='admin_material_edit'),
    path('materials/<int:pk>/delete/', views.admin_material_delete, name='admin_material_delete'),

    # Brand Management
    path('brands/', views.admin_brands, name='admin_brands'),
    path('brands/add/', views.admin_brand_add, name='admin_brand_add'),
    path('brands/<int:pk>/edit/', views.admin_brand_edit, name='admin_brand_edit'),
    path('brands/<int:pk>/delete/', views.admin_brand_delete, name='admin_brand_delete'),

    # Occasion Management
    path('occasions/', views.admin_occasions, name='admin_occasions'),
    path('occasions/add/', views.admin_occasion_add, name='admin_occasion_add'),
    path('occasions/<int:pk>/edit/', views.admin_occasion_edit, name='admin_occasion_edit'),
    path('occasions/<int:pk>/delete/', views.admin_occasion_delete, name='admin_occasion_delete'),
        path('orders/', views.admin_orders, name='admin_orders'),
    path('orders/<int:order_id>/', views.admin_order_detail, name='admin_order_detail'),
    path('orders/<int:order_id>/update-status/', views.update_order_status, name='update_order_status'),
    path('inventory/', views.admin_inventory, name='admin_inventory'),

    path('offers/', views.offer_list, name='offer_list'),
    path('offers/add/', views.add_offer, name='add_offer'),
    path('offers/edit/<int:pk>/', views.edit_offer, name='edit_offer'),
    path('offers/delete/<int:pk>/', views.delete_offer, name='delete_offer'),
    
    path('coupons/', views.coupons_list, name='admin_coupons'),
    path('coupons/add/', views.add_coupon, name='admin_add_coupon'),
    path('coupons/edit/<int:id>/', views.edit_coupon, name='admin_edit_coupon'),
    path('coupons/delete/<int:id>/', views.delete_coupon, name='admin_delete_coupon'),
    path('sales/', views.sales_report, name='sales_report'),
    path('sales/export/excel/', views.export_sales_excel, name='export_sales_excel'),
    path('sales/export/pdf/', views.export_sales_pdf, name='export_sales_pdf'),
        path('return-requests/', views.return_requests, name='return_requests'),
    path('verify-return/<int:rr_id>/', views.verify_return_request, name='verify_return'),
    path('orders/item/<int:item_id>/update-status/', views.admin_update_item_status, name='admin_update_item_status'),


]
