from django.shortcuts import render
from django.shortcuts import render, redirect,get_object_or_404
import json
from django.views.decorators.http import require_POST
from .models import Cart, CartItem, MAX_CART_QUANTITY,Wishlist,Coupon,Order,OrderItem,OrderActionLog,Payment
from products.models import Product,ProductVariant,ProductImage
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from user_section.models import Address
from django.contrib import messages
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.http import JsonResponse, HttpResponseNotAllowed
from django.db import transaction
from django.db.models import Prefetch
from weasyprint import HTML
from django.http import HttpResponse
import razorpay
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
razorpay_client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def add_to_cart(request, variant_id):
    if request.method == "POST":
        data = json.loads(request.body)
        quantity = int(data.get('quantity', 1))
        variant = get_object_or_404(ProductVariant, id=variant_id)

        # Blocked or unlisted product/category
        if not variant.product.is_active or not variant.product.category.is_active:
            return JsonResponse({'error': 'Product not available'}, status=400)

        if variant.stock == 0:
            return JsonResponse({'error': 'Product is out of stock'}, status=400)

        # Get or create user cart
        if request.user.is_authenticated:

            cart, _ = Cart.objects.get_or_create(user=request.user)

            item, created = CartItem.objects.get_or_create(cart=cart, variant=variant)

            message = "Added to cart successfully!"

            if not created:
                # Item already exists
                if item.quantity < MAX_CART_QUANTITY and item.quantity < variant.stock:
                    item.quantity += quantity
                    item.save()
                    message = f"You already have this item in your cart. Quantity increased by {quantity}."
                else:
                    return JsonResponse({'error': f'Maximum {MAX_CART_QUANTITY} quantity reached for this item.'}, status=400)
            else:
                if quantity > MAX_CART_QUANTITY:
                    quantity = MAX_CART_QUANTITY
                item.quantity = min(quantity, variant.stock)
                item.save()

            # Remove from wishlist if exists
            Wishlist.objects.filter(user=request.user, variant=variant).delete()

            return JsonResponse({
                'success': True,
                'message': message,
                'cart_count': cart.total_items()
            })
                #  Case 2: Anonymous user (session-based cart)
        else:
            cart = request.session.get('cart', {})

            variant_id_str = str(variant_id)
            if variant_id_str in cart:
                cart[variant_id_str]['quantity'] += quantity
            else:
                cart[variant_id_str] = {
                    'variant_id': variant.id, 
                    'product_name': variant.product.name,
                    'price': str(variant.price),
                    'quantity': quantity,
                    # 'image': variant.product.image.url,
                }

            request.session['cart'] = cart  
            request.session.modified = True

            return JsonResponse({
                'success': True,
                'message': "Added to cart (guest)",
                'cart_count': len(cart),
            })

    return HttpResponseNotAllowed(['POST'])


def cart_view(request):
    if request.user.is_authenticated:
        # Logged-in user cart (database)
        cart, _ = Cart.objects.get_or_create(user=request.user)
        cart_items = cart.items.select_related('variant', 'variant__product')

        for item in cart_items:
            if not item.is_in_stock():
                item.disabled = True

        context = {
            'cart_items': cart_items,
            'subtotal': cart.items_total(),
            'delivery_charge': cart.delivery_charge(),
            'total': cart.grand_total(),
            'coupons': Coupon.objects.filter(active=True, valid_to__gte=timezone.now()).order_by('-valid_to'),
            'is_guest': False,  
        }

    # else:
    #     #  Guest cart (session)
    #     session_cart = request.session.get('cart', {})
    #     cart_items = []

    #     # Convert session data into a format similar to DB cart items
    #     for variant_id, item_data in session_cart.items():
    #         print(f"🧩 Variant ID: {variant_id}")
    #         print(f"   Product Name: {item_data.get('product_name')}")
    #         print(f"   Price: {item_data.get('price')}")
    #         print(f"   Quantity: {item_data.get('quantity')}")
    #         print(f"   Image URL: {item_data.get('image')}")

    #         cart_items.append({
    #             'variant_id': variant_id,
    #             'product_name': item_data.get('product_name', ''),
    #             'price': float(item_data.get('price', 0)),
    #             'quantity': item_data.get('quantity', 1),
    #             'image': item_data.get('image', None),  # ✅ added image field
    #             'subtotal': float(item_data.get('price', 0)) * item_data.get('quantity', 1),
    #         })

    #     subtotal = sum(item['subtotal'] for item in cart_items)
    #     delivery_charge = 0 if subtotal > 1000 else 50
    #     total = subtotal + delivery_charge

    #     context = {
    #         'cart_items': cart_items,
    #         'subtotal': subtotal,
    #         'delivery_charge': delivery_charge,
    #         'total': total,
    #         'coupons': [],
    #     }
    else:
        # 👥 Guest cart (session)
        session_cart = request.session.get('cart', {})
        cart_items = []

        for variant_id, item_data in session_cart.items():
            variant_id_int = int(variant_id)

            # ✅ Fetch variant to access product info
            variant = ProductVariant.objects.filter(id=variant_id_int).select_related('product').first()

            # ✅ Fetch primary image for this variant
            primary_image = ProductImage.objects.filter(variant_id=variant_id_int, is_primary=True).first()
            image_url = primary_image.image.url if primary_image else None

            print(f"🧩 Variant {variant_id} | Product: {variant.product.name if variant else 'N/A'} | Image: {image_url}")

            cart_items.append({
                'variant': variant,  # ✅ store variant object (for same template)
                'product_name': variant.product.name if variant else item_data.get('product_name', ''),
                'price': float(item_data.get('price', 0)),
                'quantity': item_data.get('quantity', 1),
                'image': image_url,
                'subtotal': float(item_data.get('price', 0)) * item_data.get('quantity', 1),
            })

        subtotal = sum(item['subtotal'] for item in cart_items)
        delivery_charge = 0 if subtotal > 1000 else 50
        total = subtotal + delivery_charge

        context = {
            'cart_items': cart_items,
            'subtotal': subtotal,
            'delivery_charge': delivery_charge,
            'total': total,
            'coupons': [],
            'is_guest': True, 
        }

    return render(request, 'user_section/user_cart.html', context)


@require_POST
def remove_cart_item(request):
    if request.method == 'POST':
        item_id = request.POST.get('item_id')

        try:
            item = CartItem.objects.get(id=item_id, cart__user=request.user)
            cart = item.cart
            item.delete()

            return JsonResponse({
                'success': True,
                'subtotal': cart.items_total(),
                'delivery_charge': cart.delivery_charge(),
                'cart_total': cart.grand_total(),
            })
        except CartItem.DoesNotExist:
            return JsonResponse({'error': 'Item not found'}, status=404)

    return JsonResponse({'error': 'Invalid request'}, status=400)


def update_cart_quantity(request):
    if request.method == 'POST':
        item_id = request.POST.get('item_id')
        action = request.POST.get('action')

        try:
            item = CartItem.objects.get(id=item_id, cart__user=request.user)
            cart = item.cart 

            # --- Handle quantity changes ---
            if action == 'increase':
                # print(item.quantity)
                if item.quantity < MAX_CART_QUANTITY and item.quantity < item.variant.stock:
                    item.quantity += 1
                else:
                    return JsonResponse({'error': f'Maximum quantity is {MAX_CART_QUANTITY}'})
            elif action == 'decrease' and item.quantity > 1:
                item.quantity -= 1

            item.save()

            # --- Recalculate all totals ---
            subtotal = cart.items_total()
            delivery = cart.delivery_charge()
            total = cart.grand_total()
            cart_count = sum(i.quantity for i in cart.items.all())
            # print(subtotal)
            # --- Return updated values to frontend ---
            return JsonResponse({
                'quantity': item.quantity,
                'item_total': item.subtotal(),
                'subtotal': subtotal,
                'delivery_charge': delivery,
                'cart_total': total,
                'cart_count': cart_count,
            })

        except CartItem.DoesNotExist:
            return JsonResponse({'error': 'Item not found'}, status=404)

    return JsonResponse({'error': 'Invalid request'}, status=400)

def apply_coupon(request):
    """AJAX: Apply selected coupon and return updated totals."""
    if request.method == 'POST':
        code = request.POST.get('coupon_code')
        try:
            coupon = Coupon.objects.get(code__iexact=code, active=True)
        except Coupon.DoesNotExist:
            return JsonResponse({'error': 'Invalid coupon code.'}, status=400)

        cart = Cart.objects.get(user=request.user)
        subtotal = cart.items_total()
        delivery = cart.delivery_charge()

        # Check minimum purchase requirement
        if subtotal < coupon.min_purchase_amount:
            return JsonResponse({
                'error': f'Minimum purchase ₹{coupon.min_purchase_amount} required.'
            }, status=400)

        # Calculate discount
        if coupon.coupon_type.upper() == 'PERCENTAGE':
            discount = (subtotal * coupon.discount_value) / 100
        else:
            discount = coupon.discount_value

        total = max((subtotal + delivery) - discount, 0)

        #  Store coupon info in session (for checkout page)
        request.session['applied_coupon'] = coupon.code
        request.session['discount'] = float(round(discount, 2))
        request.session.modified = True  # ensure Django saves session

        return JsonResponse({
            'success': True,
            'subtotal': subtotal,
            'delivery_charge': delivery,
            'discount': round(discount, 2),
            'total': round(total, 2),
            'applied_coupon': coupon.code,
        })

    return JsonResponse({'error': 'Invalid request.'}, status=400)
# @login_required
def checkout_view(request):
    if not request.user.is_authenticated:
        request.session['redirect_after_login'] = 'checkout'
        return redirect('login')
    merge_session_cart_to_db(request)
    cart = Cart.objects.get(user=request.user)
    cart_items = cart.items.select_related('variant', 'variant__product')
    addresses = Address.objects.filter(user=request.user)

    subtotal = cart.items_total()
    delivery_charge = cart.delivery_charge()
    discount = request.session.get('discount', 0)
    applied_coupon = request.session.get('applied_coupon', '')
    total = subtotal + delivery_charge - discount
    context = {
        'addresses': addresses,
        'cart_items': cart_items,
        'subtotal': subtotal,
        'delivery_charge': delivery_charge,
        'discount': discount,
        'applied_coupon': applied_coupon,
        'total': total,
    }
    return render(request, 'user_section/checkout.html', context)

@login_required
@transaction.atomic
def place_order(request):
    if request.method == 'POST':
        user = request.user
        cart = Cart.objects.filter(user=user).first()
        if not cart or not cart.items.exists():
            messages.error(request, "Your cart is empty.")
            return redirect('cart:cart_view')

        address_id = request.POST.get('address_id')
        address = Address.objects.filter(id=address_id, user=user).first()
        if not address:
            messages.error(request, "Please select a delivery address.")
            return redirect('cart:checkout')

        applied_coupon = request.session.get('applied_coupon', None)
        subtotal = cart.items_total()
        delivery = cart.delivery_charge()
        discount = request.session.get('discount', 0)
        total = subtotal + delivery - discount

        # Create order
        payment_method = request.POST.get('payment_method', 'cod')
        order = Order.objects.create(
            user=user,
            address=address,
            subtotal=subtotal,
            delivery_charge=delivery,
            discount=discount,
            total=total,
            coupon_code=applied_coupon,
            payment_method='Razorpay' if payment_method == 'razorpay' else 'Cash on Delivery',
            status='Pending'
        )

        # Add items to order
        for item in cart.items.all():
            OrderItem.objects.create(
                order=order,
                product=item.variant.product,
                variant=item.variant,
                quantity=item.quantity,
                price=item.variant.price
            )
        # Reduce stock quantity
        item.variant.stock -= item.quantity
        if item.variant.stock < 0:
            item.variant.stock = 0  # Prevent negative stock
        item.variant.save()    

        # Clear cart
        cart.items.all().delete()
          #  Send order confirmation email
        subject = f"Your Order {order.iorderid} has been placed successfully!"
        html_message = render_to_string('emails/order_confirmation.html', {'order': order, 'user': user})
        plain_message = strip_tags(html_message)
        from_email = 'savithan156@gmail.com'
        to_email = [user.email]

        send_mail(subject, plain_message, from_email, to_email, html_message=html_message)
        print(payment_method)
        if payment_method == 'cod':
            order.status = "Placed"
            order.payment_status = "Pending"
            order.save()
            return redirect('cart:order_success', order_id=order.id)
        amount_paise = int(total * 100)
        DATA = {
            "amount": amount_paise,
            "currency": "INR",
            "receipt": f"order_rcpt_{order.id}",
            "payment_capture": 1
        }
        razorpay_order = razorpay_client.order.create(data=DATA)
        razorpay_order_id = razorpay_order['id']

        order.razorpay_order_id = razorpay_order_id
        order.save()
        #  Render Razorpay payment page
        context = {
            'order': order,
            'amount': amount_paise,
            'razorpay_order_id': razorpay_order_id,
            'razorpay_key': settings.RAZORPAY_KEY_ID,
            'currency': 'INR',
        }
        return render(request, 'user_section/razorpay_checkout.html', context)


        # Redirect to success page
        # return redirect('cart:order_success', order_id=order.id)

    return redirect('checkout')
@csrf_exempt
def razorpay_success(request):
    if request.method == "POST":
        payment_id = request.POST.get('razorpay_payment_id')
        razorpay_order_id = request.POST.get('razorpay_order_id')
        signature = request.POST.get('razorpay_signature')
        order_id = request.POST.get('order_id')

        order = get_object_or_404(Order, id=order_id)

        params_dict = {
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature
        }

        try:
            razorpay_client.utility.verify_payment_signature(params_dict)
        except razorpay.errors.SignatureVerificationError:
            order.payment_status = 'Failed'
            order.status = 'Payment Failed'
            order.save()
            messages.error(request, "Payment verification failed.")
            return redirect('cart:order_success', order_id=order.id)

        # ✅ Payment verified
        order.payment_status = 'Paid'
        order.status = 'Placed'
        order.razorpay_payment_id = payment_id
        order.razorpay_signature = signature
        order.save()

        return redirect('cart:order_success', order_id=order.id)

    return redirect('cart:checkout')

def set_default_address(request, address_id):
    """Sets the selected address as the default one for the user."""
    address = get_object_or_404(Address, id=address_id, user=request.user)

    # Unset any existing default
    Address.objects.filter(user=request.user, is_default=True).update(is_default=False)

    # Set new default
    address.is_default = True
    address.save()

    messages.success(request, "Default address updated successfully.")
    return redirect('checkout')  # redirect back to checkout page
@login_required
def order_success(request, order_id):
    order = Order.objects.get(id=order_id, user=request.user)
    # print(f"Order ID: {order.id}, Total: {order.total}, User: {order.user_id}")
    # return render(request, 'user_section/order_success.html', {'order': order})
    total_str = f"{order.total:.2f}" if order.total else "0.00"
    return render(request, 'user_section/order_success.html', {'order': order, 'total_str': total_str})
# def order_detail(request, order_id):
#     order = get_object_or_404(Order, id=order_id, user=request.user)
#     return render(request, 'user_section/order_detail.html', {'order': order})

@login_required
def download_invoice(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    html_string = render_to_string('user_section/invoice.html', {'order': order})
    
    html = HTML(string=html_string, base_url=request.build_absolute_uri('/'))
    
    pdf = html.write_pdf()  

    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename=Invoice_{order.iorderid}.pdf'
    return response
@login_required

def order_detail(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)

    # Prefetch ONLY primary images for each variant
    primary_images = Prefetch(
        'variant__images',
        queryset=ProductImage.objects.filter(is_primary=True),
        to_attr='primary_image'
    )

    order_items = (
        order.items
        .select_related('variant', 'product')
        .prefetch_related(primary_images)
    )

    return render(request, 'user_section/order_detail.html', {
        'order': order,
        'order_items': order_items
    })
@login_required
@transaction.atomic
def cancel_order(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        # allow cancellation only if not delivered or already cancelled
        if order.status in ['Delivered', 'Cancelled']:
            return JsonResponse({'error': 'Order cannot be cancelled.'}, status=400)
        # mark items cancelled & increment variant stock
        for item in order.items.filter(cancelled=False):
            variant = item.variant
            variant.stock = (variant.stock or 0) + item.quantity
            variant.save()
            item.cancelled = True
            item.save()
            OrderActionLog.objects.create(order=order, item=item, user=request.user,
                                          action='CancelItem', reason=reason)
        order.status = 'Cancelled'
        order.save()
        OrderActionLog.objects.create(order=order, user=request.user,
                                      action='CancelOrder', reason=reason)
        return JsonResponse({'success': True, 'message': 'Order cancelled.'})
    return JsonResponse({'error': 'Invalid request'}, status=400)
@login_required
@transaction.atomic
def cancel_order_item(request, order_id, item_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    item = get_object_or_404(OrderItem, id=item_id, order=order)
    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        if item.cancelled:
            return JsonResponse({'error': 'Item already cancelled.'}, status=400)
        if order.status == 'Delivered':
            return JsonResponse({'error': 'Cannot cancel item of delivered order.'}, status=400)
        # update stock
        variant = item.variant
        variant.stock = (variant.stock or 0) + item.quantity
        variant.save()
        item.cancelled = True
        item.save()
        OrderActionLog.objects.create(order=order, item=item, user=request.user,
                                      action='CancelItem', reason=reason)
        # if all items cancelled -> mark order cancelled
        if not order.items.filter(cancelled=False).exists():
            order.status = 'Cancelled'
            order.save()
            OrderActionLog.objects.create(order=order, user=request.user,
                                          action='CancelOrder', reason='All items cancelled')
        return JsonResponse({'success': True})
    return JsonResponse({'error': 'Invalid'}, status=400)
@login_required
@transaction.atomic
def return_order(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        if not reason:
            return JsonResponse({'error':'Return reason required.'}, status=400)
        if order.status != 'Delivered':
            return JsonResponse({'error': 'Only delivered orders can be returned.'}, status=400)
        # mark as returned 
        for item in order.items.filter(returned=False, cancelled=False):
            item.returned = True
            item.save()
            #  adjust stock
            variant = item.variant
            variant.stock = (variant.stock or 0) + item.quantity
            variant.save()
            OrderActionLog.objects.create(order=order, item=item, user=request.user,
                                          action='ReturnItem', reason=reason)
        order.status = 'Returned'
        order.save()
        OrderActionLog.objects.create(order=order, user=request.user,
                                      action='ReturnOrder', reason=reason)
        return JsonResponse({'success': True, 'message': 'Your order has been successfully returned.'})
    return JsonResponse({'error': 'Invalid request'}, status=400)

def merge_session_cart_to_db(request):
    """
    Merge guest session cart items into user's database cart after login.
    """
    session_cart = request.session.get('cart', {})
    if not session_cart:
        return

    cart, _ = Cart.objects.get_or_create(user=request.user)

    for variant_id, item_data in session_cart.items():
        try:
            variant = ProductVariant.objects.get(id=int(variant_id))
            quantity = int(item_data.get('quantity', 1))
            item, created = CartItem.objects.get_or_create(cart=cart, variant=variant)

            if not created:
                # If already exists → increase quantity but not beyond stock
                item.quantity = min(item.quantity + quantity, variant.stock)
            else:
                item.quantity = min(quantity, variant.stock)
            item.save()

        except ProductVariant.DoesNotExist:
            continue  # Ignore deleted variants gracefully

    request.session['cart'] = {}
    request.session.modified = True
