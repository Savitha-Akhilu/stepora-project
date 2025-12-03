from django.shortcuts import render
from django.shortcuts import render, redirect,get_object_or_404
import json
from django.views.decorators.http import require_POST
from .models import Cart, CartItem, MAX_CART_QUANTITY,Wishlist,Coupon,Order,OrderItem,OrderActionLog,Payment
from products.models import Product,ProductVariant,ProductImage
# from django.http import JsonResponse
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
from decimal import Decimal
from django.views.decorators.csrf import csrf_exempt
from .utils import get_variant_image
from adminpanel.utils import get_best_offer_price
from user_section.models import ReturnRequest,Wallet,WalletTransaction
from stepora.utils.logging import get_logger
logger = get_logger()


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
                    # return JsonResponse({'error': f'Maximum {MAX_CART_QUANTITY} quantity reached for this item.'}, status=400)
                    if item.quantity >= MAX_CART_QUANTITY:
                        return JsonResponse(
                            {'error': f'Maximum limit ({MAX_CART_QUANTITY}) reached for this product.'},
                            status=400
                        )

                    if item.quantity >= variant.stock:
                        return JsonResponse(
                                {'error': f'Only {variant.stock} quantity available in stock.'},
                                status=400
                            )
            else:
                if quantity > MAX_CART_QUANTITY:
                    quantity = MAX_CART_QUANTITY
                item.quantity = min(quantity, variant.stock)
                item.save()

            # Remove from wishlist if exists
            Wishlist.objects.filter(user=request.user, variant=variant).delete()
            coupon_code = request.session.get('applied_coupon')
            # print
            if coupon_code:
                try:
                    coupon = Coupon.objects.get(code=coupon_code, active=True)
                    cart.apply_coupon(coupon)  # call your cart's coupon logic
                except Coupon.DoesNotExist:
                    # Coupon no longer valid → remove it
                    if 'applied_coupon' in request.session:
                        del request.session['applied_coupon']

            # Recalculate totals
            cart.calculate_totals()
            return JsonResponse({
                'success': True,
                'message': message,
                'cart_count': cart.total_items(),
                'cart_total': str(cart.get_final_amount()),
            })
                #  Case 2: not logged user (session-based cart)
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
        # cart_items = cart.items.select_related('variant', 'variant__product')
        cart_items = cart.get_items_with_offer()

        # ---  offer and delivery logic ---
        subtotal = Decimal(cart.items_offer_total())  
        delivery_charge = cart.delivery_charge()    
        tax_rate = Decimal('0.18')
        tax_amount = subtotal * tax_rate
   
        total = cart.grand_total()+tax_amount                

        # --- Mark out-of-stock items ---
        for item in cart_items:
            if not item.is_in_stock():
                item.disabled = True
            item.image_url = get_variant_image(item.variant)    

        # --- Original subtotal before offers 
        original_total = Decimal(cart.items_total())
        savings = original_total - subtotal
        # --- check first order ---
        discount = Decimal(request.session.get('discount', 0))

        # --- Coupon recalculation ---
        applied_coupon = request.session.get('applied_coupon')
        discount = Decimal('0.00')

        if applied_coupon:
            try:
                coupon = Coupon.objects.get(code__iexact=applied_coupon, active=True)

                if coupon.is_valid_for(subtotal):
                    discount = Decimal(coupon.apply_discount(subtotal))
                    total = max(total - discount, Decimal('0.00'))

            except Coupon.DoesNotExist:
                pass
        
        context = {
            'cart_items': cart_items,
            'subtotal': round(subtotal, 2),
            'original_total': round(original_total, 2),
            'delivery_charge': delivery_charge,
            'total': round(total, 2),
            'savings': round(savings, 2),
            'applied_coupon': applied_coupon,
            'discount': round(Decimal(discount), 2),
            'tax_amount': round(tax_amount, 2),
            'coupons': Coupon.objects.filter(
                active=True,
                valid_from__lte=timezone.now(),
                valid_to__gte=timezone.now()
            ).order_by('-valid_to'),
            'is_guest': False,
        }

    else:
        # Guest user: stored in session
        session_cart = request.session.get('cart', {})
        cart_items = []
        subtotal = Decimal('0.00')

        for variant_id, item_data in session_cart.items():
            variant = ProductVariant.objects.filter(id=variant_id).select_related('product').first()
            if not variant:
                continue

            from adminpanel.utils import get_best_offer_price
            final_price, discount_percent, offer = get_best_offer_price(variant)
            variant.final_price = final_price
            variant.has_offer = True if offer else False

            image_url = get_variant_image(variant)

            item_subtotal = Decimal(final_price) * item_data.get('quantity', 1)
            subtotal += item_subtotal

            cart_items.append({
                'variant': variant,
                'product_name': variant.product.name,
                'price': float(final_price),
                'quantity': item_data.get('quantity', 1),
                'image_url': image_url,
                'subtotal': float(item_subtotal),
            })

        # Delivery charge logic
        if subtotal == 0:
            delivery_charge = 0
        elif subtotal < 1000:
            delivery_charge = 50
        elif subtotal < 3000:
            delivery_charge = 30
        else:
            delivery_charge = 0
        tax_rate = Decimal('0.18')
        tax_amount = subtotal * tax_rate

        total = subtotal + tax_amount + Decimal(delivery_charge)


        # total = subtotal + Decimal(delivery_charge)
        original_total = Decimal('0.00')
        for item in cart_items:
            product_price = Decimal(item['variant'].price)
            item_original = product_price * item['quantity']
            original_total += item_original

        savings = original_total - subtotal

        applied_coupon = None
        discount = Decimal('0.00')

        context = {
            'cart_items': cart_items,
            'subtotal': round(subtotal, 2),
            'original_total': round(original_total, 2),
            'delivery_charge': delivery_charge,
            'total': round(total, 2),
            'savings': round(savings, 2),
            'applied_coupon': applied_coupon,
            'discount': round(discount, 2),
            'coupons': [],
            'tax_amount': round(tax_amount, 2),
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
            logger.info(f"Cart item removed: user={request.user.id}, item_id={item_id}")

            if not cart.items.exists():
                logger.info(
                      f"Last item removed; coupon cleared: user={request.user.id}, item_id={item_id}")
                # Clear coupon 
                request.session.pop('applied_coupon', None)
                request.session.pop('discount', None)
                if hasattr(cart, 'coupon'):
                    cart.coupon = None
                    cart.save()
                return JsonResponse({
                    'success': True,
                    'subtotal': 0,
                    'original_total': 0,
                    'savings': 0,
                    'delivery_charge': 0,
                    'total': 0,
                    'applied_coupon': '',
                    'discount': 0,
                    'cart_count': 0,
                    'tax_amount': 0,

                })


            # --- Offer recalculations ---
            subtotal = Decimal(cart.items_offer_total())
            delivery_charge = Decimal(cart.delivery_charge())
            tax_rate = Decimal('0.18')
            tax_amount = subtotal * tax_rate
            # total = Decimal(cart.grand_total())+tax_amount
            total = subtotal + tax_amount + delivery_charge
            original_total = Decimal(cart.items_total())
            savings = original_total - subtotal

            applied_coupon_code = request.session.get('applied_coupon')
            discount = Decimal('0.00')

            if applied_coupon_code:
                try:
                    coupon = Coupon.objects.get(code__iexact=applied_coupon_code, active=True)
                    if coupon.is_valid_for(subtotal):
                        discount = Decimal(coupon.apply_discount(subtotal))
                        total = max(total - discount, Decimal('0.00'))
                    else:
                        #  Remove invalid coupon (subtotal below min)
                        logger.warning(
                          f"Coupon removed due to subtotal below minimum: user={request.user.id}, coupon={applied_coupon_code}")
                        request.session.pop('applied_coupon', None)
                        request.session.pop('discount', None)
                        request.session.modified = True
                except Coupon.DoesNotExist:
                    logger.error(
                       f"Coupon not found, removed from session: user={request.user.id}, coupon={applied_coupon_code}")
                    request.session.pop('applied_coupon', None)
                    request.session.pop('discount', None)


            cart_count = sum(i.quantity for i in cart.items.all())

            return JsonResponse({
                'success': True,
                'subtotal': float(round(subtotal, 2)),
                'original_total': float(round(original_total, 2)),
                'savings': float(round(savings, 2)),
                'delivery_charge': float(round(delivery_charge, 2)),
                'total': float(round(total, 2)),
                'applied_coupon': applied_coupon_code or '',
                'discount': float(round(discount, 2)),
                'cart_count': cart_count,
                'tax_amount': float(round(tax_amount, 2)),

            })

        except CartItem.DoesNotExist:
            logger.error(
                  f"Cart item remove failed: item_id={item_id} not found for user={request.user.id}")

            return JsonResponse({'error': 'Item not found'}, status=404)

    return JsonResponse({'error': 'Invalid request'}, status=400)

def update_cart_quantity(request):
    if request.method == 'POST':
        item_id = request.POST.get('item_id')
        action = request.POST.get('action')

        try:
            item = CartItem.objects.get(id=item_id, cart__user=request.user)
            cart = item.cart
            old_qty = item.quantity  # before update
            # --- Handle quantity changes ---
            if action == 'increase':
                if item.quantity < MAX_CART_QUANTITY and item.quantity < item.variant.stock:
                    item.quantity += 1
                else:
                    return JsonResponse({'error': f'Maximum quantity is {MAX_CART_QUANTITY}'})
            elif action == 'decrease' and item.quantity > 1:
                item.quantity -= 1
            new_qty = item.quantity  # before update
    

            item.save()
            logger.info(
                f"Cart quantity updated: user={request.user.id}, item={item_id}, "
                f"{old_qty} → {new_qty}"
            )            # --- Get offer price ---
            final_price, discount_percent, offer = get_best_offer_price(item.variant)
            item_total = Decimal(final_price) * item.quantity

            # --- Offer logic ---
            subtotal = Decimal(cart.items_offer_total())
            delivery_charge = Decimal(cart.delivery_charge())
            tax_rate = Decimal('0.18')
            tax_amount = subtotal * tax_rate

            # total = Decimal(cart.grand_total())+tax_amount
            total = subtotal + tax_amount + delivery_charge
            subtotal
            # print("update cart",total)

            # --- Original subtotal (before offers) ---
            original_total = Decimal(cart.items_total())
            savings = original_total - subtotal  # discount from offers


            applied_coupon_code = request.session.get('applied_coupon')
            discount = Decimal('0.00')
            coupon_removed = False

            if applied_coupon_code:
                try:
                    coupon = Coupon.objects.get(code__iexact=applied_coupon_code, active=True)
                    if coupon.is_valid_for(subtotal):
                        discount = Decimal(coupon.apply_discount(subtotal))
                        total = max(total - discount, Decimal('0.00'))
                    else:
                        # ❌ Remove coupon if subtotal below min purchase or expired
                        request.session.pop('applied_coupon', None)
                        request.session.pop('discount', None)
                        request.session.modified = True
                        coupon_removed = True
                except Coupon.DoesNotExist:
                    logger.error(
                        f"Coupon not found and removed: user={request.user.id}, "
                        f"coupon={applied_coupon_code}"
                    )
                    request.session.pop('applied_coupon', None)
                    request.session.pop('discount', None)
                    coupon_removed = True
            cart_count = sum(i.quantity for i in cart.items.all())

            #  Return same data structure as cart_view context
            return JsonResponse({
                'quantity': item.quantity,
                'item_total': float(round(item_total, 2)),
                'subtotal': float(round(subtotal, 2)),
                'original_total': float(round(original_total, 2)),
                'savings': float(round(savings, 2)),
                'delivery_charge': float(round(delivery_charge, 2)),
                'total': float(round(total, 2)),
                'applied_coupon': applied_coupon_code or '',
                'discount': float(round(discount, 2)),
                'cart_count': cart_count,
                'tax_amount': float(round(tax_amount, 2)),

            })

        except CartItem.DoesNotExist:
            logger.error(
                f"Cart update failed: item={item_id} does not exist for user={request.user.id}"
            )
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

        #  Clear any previously applied coupon before applying new one
        request.session.pop('applied_coupon', None)
        request.session.pop('discount', None)

        cart = Cart.objects.get(user=request.user)
        subtotal = cart.items_offer_total()
        mrp=cart.items_total()
        delivery = cart.delivery_charge()
# --- TAX (18%) ---
        tax_amount = subtotal * Decimal("0.18")
        tax_amount = tax_amount.quantize(Decimal("0.01"))

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

        # total = max((subtotal + delivery+tax_amount) - discount, 0)
        total = subtotal + tax_amount + delivery - discount


        # Save only the new coupon
        request.session['applied_coupon'] = coupon.code
        request.session['discount'] = float(round(discount, 2))
        request.session.modified = True

        return JsonResponse({
            'success': True,
            'subtotal': round(subtotal, 2),
            'delivery_charge': delivery,
            'discount': round(discount, 2),
            'total': round(total, 2),
            'applied_coupon': coupon.code,
            'mrp':mrp,
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
    for item in cart_items:
        item.image_url = get_variant_image(item.variant)

    # subtotal = cart.items_total()
    subtotal = Decimal(cart.items_offer_total())  # <-- discounted total

    delivery_charge = cart.delivery_charge()
    discount = request.session.get('discount', 0)
    applied_coupon = request.session.get('applied_coupon', '')
    tax_rate = Decimal('0.18')
    tax_amount = subtotal * tax_rate
    # total = Decimal(subtotal) + Decimal(delivery_charge) - Decimal(discount)
    total = Decimal(subtotal) + tax_amount + Decimal(delivery_charge) - Decimal(discount)
    wallet, _ = Wallet.objects.get_or_create(user=request.user)
    context = {
        'addresses': addresses,
        'cart_items': cart_items,
        'subtotal': subtotal,
        'delivery_charge': delivery_charge,
        'discount': discount,
        'applied_coupon': applied_coupon,
        'total': total,
        'wallet': wallet,  
        'tax_amount': round(tax_amount, 2),

    }
    return render(request, 'user_section/checkout.html', context)

@login_required
def place_order_without_razor(request):
    if request.method == 'POST':
        user = request.user
        cart = Cart.objects.filter(user=user).first()
        if not cart or not cart.items.exists():
            messages.error(request, "Your cart is empty.")
            return redirect('cart:cart')

        address_id = request.POST.get('address_id')
        address = Address.objects.filter(id=address_id, user=user).first()
        if not address:
            messages.error(request, "Please select a delivery address.")
            return redirect('cart:checkout')

        applied_coupon = request.session.get('applied_coupon', None)
        subtotal = Decimal(cart.items_offer_total())  #  includes product-level offers
        delivery = Decimal(cart.delivery_charge())
        discount = Decimal(request.session.get('discount', 0))
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
        # print(payment_method)
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

@transaction.atomic
def place_order_error_nov7(request):
    if request.method == 'POST':
        user = request.user
        cart = Cart.objects.filter(user=user).first()

        if not cart or not cart.items.exists():
            messages.error(request, "Your cart is empty.")
            return redirect('cart:cart')

        address_id = request.POST.get('address_id')
        address = Address.objects.filter(id=address_id, user=user).first()
        if not address:
            messages.error(request, "Please select a delivery address.")
            return redirect('cart:checkout')

        applied_coupon = request.session.get('applied_coupon', None)
        subtotal = cart.items_total()
        delivery = cart.delivery_charge()
        discount = Decimal(request.session.get('discount', 0))
        total = subtotal + delivery - discount

        payment_method = request.POST.get('payment_method', 'cod')

        try:
            with transaction.atomic():
                #  Create the order
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

                # Add each item and reduce stock
                for item in cart.items.all():
                    OrderItem.objects.create(
                        order=order,
                        product=item.variant.product,
                        variant=item.variant,
                        quantity=item.quantity,
                        price=item.variant.price
                    )
                    item.variant.stock = max(item.variant.stock - item.quantity, 0)
                    item.variant.save()

                #  Create Payment entry
                payment = Payment.objects.create(
                    order=order,
                    user=user,
                    method='Razorpay' if payment_method == 'razorpay' else 'COD',
                    amount=total,
                    status='Pending'
                )

                # Send confirmation email (after DB commit)
                def send_email_after_commit():
                    subject = f"Your Order {order.iorderid} has been placed successfully!"
                    html_message = render_to_string('emails/order_confirmation.html', {'order': order, 'user': user})
                    plain_message = strip_tags(html_message)
                    from_email = settings.DEFAULT_FROM_EMAIL
                    to_email = [user.email]
                    send_mail(subject, plain_message, from_email, to_email, html_message=html_message)

                transaction.on_commit(send_email_after_commit)

                # Cash on Delivery 
                if payment_method == 'cod':
                    payment.status = 'Success'
                    payment.save()

                    order.status = 'Placed'
                    order.save()

                    cart.items.all().delete()
                    return redirect('cart:order_success', order_id=order.id)

                #  Razorpay flow
                amount_paise = int(total * 100)
                DATA = {
                    "amount": amount_paise,
                    "currency": "INR",
                    "receipt": f"order_rcpt_{order.id}",
                    "payment_capture": 1
                }

                razorpay_order = razorpay_client.order.create(data=DATA)
                payment.provider_order_id = razorpay_order['id']
                payment.save()

                context = {
                    'order': order,
                    'payment': payment,
                    'amount': amount_paise,
                    'razorpay_order_id': razorpay_order['id'],
                    'razorpay_key': settings.RAZORPAY_KEY_ID,
                    'currency': 'INR',
                }
                return render(request, 'user_section/razorpay_checkout.html', context)

        except Exception as e:
            print("❌ Order creation failed:", e)
            messages.error(request, "Something went wrong while placing your order. Please try again.")
            return redirect('cart:checkout')

    return redirect('cart:checkout')


def place_order(request):
    if request.method == 'POST':
        user = request.user
        cart = Cart.objects.filter(user=user).first()

        if not cart or not cart.items.exists():
            messages.error(request, "Your cart is empty.")
            return redirect('cart:cart')

        address_id = request.POST.get('address_id')
        address = Address.objects.filter(id=address_id, user=user).first()
        if not address:
            messages.error(request, "Please select a delivery address.")
            return redirect('cart:checkout')

        payment_method = request.POST.get('payment_method', 'cod')
        use_wallet = request.POST.get('use_wallet') == 'on'   
        applied_coupon_code = request.session.get('applied_coupon', None)

        #  Subtotal 
        subtotal = Decimal(cart.items_offer_total())

        #  Delivery based on  total
        delivery = Decimal(cart.delivery_charge())
# --- TAX Calculation ---
        tax_rate = Decimal('0.18')
        tax_amount = subtotal * tax_rate

        #  Coupon discount
        discount = Decimal('0.00')
        coupon_discount = Decimal('0.00')
        coupon_obj = None
        if applied_coupon_code:
            try:
                coupon_obj = Coupon.objects.get(code__iexact=applied_coupon_code, active=True)
                coupon_discount = Decimal(coupon_obj.calculate_discount(subtotal))
            except Coupon.DoesNotExist:
                request.session.pop('applied_coupon', None)

        #  Total after offers, coupon, and delivery
        total = subtotal + tax_amount+delivery - discount - coupon_discount
        items_total = cart.items_total()                  # without ofr
        discount = items_total - subtotal              # total discount
        wallet_used = Decimal('0.00')
        remaining_amount = total

        wallet, _ = Wallet.objects.get_or_create(user=user)

        if use_wallet and wallet.balance > 0:
            if wallet.balance >= total:
                wallet_used = total
                remaining_amount = Decimal('0.00')
                wallet.balance -= total
            else:
                wallet_used = wallet.balance
                remaining_amount -= wallet.balance
                wallet.balance = Decimal('0.00')
            wallet.save()

            # Create wallet transaction 
            WalletTransaction.objects.create(
                wallet=wallet,
                transaction_type='DEBIT',
                amount=wallet_used,
                description=f"Used for checkout"
            )

        try:
            with transaction.atomic():
                #  Create Order
                order = Order.objects.create(
                    user=user,
                    address=address,
                    subtotal=subtotal,
                    delivery_charge=delivery,
                    discount=discount,
                    total=total,
                    coupon=coupon_obj,
                    coupon_code=applied_coupon_code,
                    coupon_discount=coupon_discount,
                    payment_method='WALLET' if remaining_amount == 0 else ('RAZORPAY' if payment_method == 'razorpay' else 'COD'),
                    # payment_method='RAZORPAY' if payment_method == 'razorpay' else 'COD',
                    status='Pending'
                )

                #  Add Order Items (with offer data)
                total_offer_discount = Decimal('0.00')
                for item in cart.items.all():
                    final_price, discount_amount, offer = get_best_offer_price(item.variant)
                    total_offer_discount += discount_amount * item.quantity

                    OrderItem.objects.create(
                        order=order,
                        product=item.variant.product,
                        variant=item.variant,
                        offer=offer,
                        discount_value=discount_amount,
                        quantity=item.quantity,
                        price=item.variant.price  # original MRP
                    )

                    #  Reduce stock
                    item.variant.stock = max(item.variant.stock - item.quantity, 0)
                    item.variant.save()

                #  Update order with total offer discount
                order.subtotal = subtotal
                order.save(update_fields=['subtotal'])

                #  Create Payment entry
                payment = Payment.objects.create(
                    order=order,
                    user=user,
                    # method='RAZORPAY' if payment_method == 'razorpay' else 'COD',
                    method='WALLET' if remaining_amount == 0 else ('RAZORPAY' if payment_method == 'razorpay' else 'COD'),
                    amount=total,
                    status='Pending'
                )

                #  email 
                def send_email_after_commit():
                    subject = f"Your Order {order.iorderid} has been placed successfully!"
                    html_message = render_to_string('emails/order_confirmation.html', {'order': order, 'user': user})
                    plain_message = strip_tags(html_message)
                    send_mail(subject, plain_message, settings.DEFAULT_FROM_EMAIL, [user.email], html_message=html_message)

                transaction.on_commit(send_email_after_commit)
                # --- Wallt only ---
                if remaining_amount == 0:
                    payment.status = 'Success'
                    payment.save()

                    order.status = 'Processing'
                    order.payment_method = 'WALLET'
                    order.save()

                    cart.items.all().delete()

                    messages.success(request, "Order placed successfully using wallet balance.")
                    return redirect('cart:order_success', order_id=order.id)
                #  COD Flow
                if payment_method == 'cod':
                    payment.status = 'Pending'
                    payment.save()
                    order.status = 'Processing'
                    order.save()

                    cart.items.all().delete()
                    return redirect('cart:order_success', order_id=order.id)

                #  Razorpay Flow
                if payment_method == 'razorpay':
                # Pass reduced amount (after wallet deduction)
                    amount_paise = int(remaining_amount * 100)
                    DATA = {
                        "amount": amount_paise,
                        "currency": "INR",
                        "receipt": f"order_rcpt_{order.id}",
                        "payment_capture": 1
                    }
                    razorpay_order = razorpay_client.order.create(data=DATA)
                    payment.provider_order_id = razorpay_order['id']
                    payment.amount = remaining_amount 
                    payment.save()

                    context = {
                        'order': order,
                        'payment': payment,
                        'amount': amount_paise,
                        'razorpay_order_id': razorpay_order['id'],
                        'razorpay_key': settings.RAZORPAY_KEY_ID,
                        'currency': 'INR',
                        'wallet_used': wallet_used,
                    }
                    return render(request, 'user_section/razorpay_checkout.html', context)

        except Exception as e:
            print(" Order creation failed:", e)
            messages.error(request, "Something went wrong while placing your order. Please try again.")
            return redirect('cart:checkout')


    return redirect('cart:checkout')


@csrf_exempt
def razorpay_success(request):
    if request.method == "POST":
        payment_id = request.POST.get('razorpay_payment_id')
        razorpay_order_id = request.POST.get('razorpay_order_id')
        signature = request.POST.get('razorpay_signature')
        order_id = request.POST.get('order_id')

        order = get_object_or_404(Order, id=order_id)
        payment = order.payments.order_by('-id').first()
        params_dict = {
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature
        }

        try:
            razorpay_client.utility.verify_payment_signature(params_dict)
        except razorpay.errors.SignatureVerificationError:
            order.status = 'Cancelled'
            order.save()
            if payment:
                payment.status = 'Failed'
                payment.save()
            messages.error(request, "Payment verification failed.")
            return redirect('cart:payment_failed', order_id=order.id)
            # return redirect('cart:order_success', order_id=order.id)

        #  Payment successful
        order.status = 'Processing'
        # order.razorpay_payment_id = payment_id
        # order.razorpay_signature = signature
        order.save()

        if payment:
            payment.status = 'Success'
            payment.provider_signature = signature
            payment.provider_payment_id = payment_id
            payment.provider_order_id = razorpay_order_id
            payment.save()

        Cart.objects.filter(user=order.user).delete()
        request.session.pop('applied_coupon', None)
        request.session.pop('discount', None)
        request.session.modified = True

        messages.success(request, " Payment successful! Your order has been placed.")
        return redirect('cart:order_success', order_id=order.id)

    return redirect('cart:checkout')
@login_required
def payment_failed(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    return render(request, 'user_section/payment_failed.html', {'order': order})
@csrf_exempt
@login_required
def razorpay_failed(request, order_id):
    """Handle failed Razorpay payments."""
    order = get_object_or_404(Order, id=order_id, user=request.user)
    payment = order.payments.order_by('-id').first()

    # Update statuses
    order.status = 'Failed'
    order.save(update_fields=['status'])

    if payment:
        payment.status = 'Failed'
        payment.save(update_fields=['status'])

    return redirect('cart:payment_failed', order_id=order.id)

@login_required
def retry_payment(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    payment = order.payments.order_by('-id').first()

    remaining_amount = order.total
    amount_paise = int(remaining_amount * 100)

    DATA = {
        "amount": amount_paise,
        "currency": "INR",
        "receipt": f"retry_rcpt_{order.id}",
        "payment_capture": 1
    }

    # Create new Razorpay order
    razorpay_order = razorpay_client.order.create(data=DATA)

    # Update payment record
    payment.provider_order_id = razorpay_order['id']
    payment.status = 'Pending'
    payment.amount = remaining_amount
    payment.save()

    context = {
        'order': order,
        'payment': payment,
        'amount': amount_paise,
        'razorpay_order_id': razorpay_order['id'],
        'razorpay_key': settings.RAZORPAY_KEY_ID,
        'currency': 'INR',
    }

    return render(request, 'user_section/razorpay_checkout.html', context)


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
    # After successful order creation

    request.session.pop('applied_coupon', None)
    request.session.pop('discount', None)
    request.session.modified = True

    order = Order.objects.get(id=order_id, user=request.user)
    total_str = f"{order.total:.2f}" if order.total else "0.00"
    return render(request, 'user_section/order_success.html', {'order': order, 'total_str': total_str})


@login_required
def download_invoice(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    order_items = order.items.select_related('variant', 'product')

    total_mrp = Decimal('0.00')
    offer_discount = Decimal('0.00')
    coupon_discount = order.coupon_discount or Decimal('0.00')
    delivery_charge = order.delivery_charge or Decimal('0.00')

    #  Calculate totals and discounts
    for item in order_items:
        item_total_mrp = item.price * item.quantity
        item_offer_total = item.final_price * item.quantity
        item.item_subtotal = item.final_price * item.quantity
        total_mrp += item_total_mrp
        offer_discount += (item_total_mrp - item_offer_total)

    subtotal = total_mrp - offer_discount
    # --- TAX (18%) ---
    tax_amount = subtotal * Decimal('0.18')
    tax_amount = tax_amount.quantize(Decimal("0.01"))

    total = subtotal - coupon_discount + delivery_charge+tax_amount

    #  Send all values to template
    context = {
        'order': order,
        'order_items': order_items,
        'total_mrp': total_mrp,
        'offer_discount': offer_discount,
        'coupon_discount': coupon_discount,
        'delivery_charge': delivery_charge,
        'subtotal': subtotal,
        'total': total,
        'tax_amount': tax_amount,     
    }

    html_string = render_to_string('user_section/invoice.html', context)
    html = HTML(string=html_string, base_url=request.build_absolute_uri('/'))
    pdf = html.write_pdf()

    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename=Invoice_{order.iorderid}.pdf'
    return response

@login_required
def order_detail(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)

    primary_images = Prefetch(
        'variant__images',
        queryset=ProductImage.objects.filter(is_primary=True),
        to_attr='primary_image'
    )

    # Fetch offer details also
    order_items = (
        order.items
        .select_related('variant', 'product', 'offer')  # include offer
        .prefetch_related(primary_images)
    )

    for item in order_items:
        item.subtotal = item.final_price * item.quantity
        item.variant.final_price = item.final_price
        item.variant.price = item.price
        item.variant.has_offer = True if item.discount_value > 0 else False

        # Attach readable offer info
        if item.offer:
            item.offer_title = item.offer.name or "Special Offer"
            item.offer_amount = item.discount_value
        else:
            item.offer_title = None
            item.offer_amount = None
    # print(order)
    # --- TAX (18%) ---
    tax_rate = Decimal('0.18')
    tax_amount = order.subtotal * tax_rate

    context = {
        'order': order,
        'order_items': order_items,
        'tax_amount': round(tax_amount, 2),

    }
    return render(request, 'user_section/order_detail.html', context)


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
    item = get_object_or_404(OrderItem, id=item_id, order__user=request.user)
    order = get_object_or_404(Order, id=order_id, user=request.user)
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request'}, status=400)

    reason = request.POST.get('reason', '').strip()
    if not reason:
        return JsonResponse({'error': 'Cancellation reason required.'}, status=400)

    if item.status not in ['Pending', 'Processing']:
        return JsonResponse({'error': 'This item cannot be cancelled.'}, status=400)
    active_items_count = order.items.filter(cancelled=False, returned=False).count()
    if active_items_count == 1:
        delivery_refund = Decimal(order.delivery_charge or 0)
    else:
        delivery_refund = Decimal('0.00')

    item.cancelled = True
    item.status = 'Cancelled'
    item.save()

    # restore stock
    variant = item.variant
    variant.stock = (variant.stock or 0) + item.quantity
    variant.save()

    OrderActionLog.objects.create(order=order, item=item, user=request.user, action='CancelItem', reason=reason)
    if order.payment_method.lower() in ['razorpay', 'wallet']:
        order_items = order.items.all()

        # Step 1: Find sum of all item totals
        order_total_price = sum(
            Decimal(i.final_price) * i.quantity for i in order_items
        )

        item_total = Decimal(item.final_price) * item.quantity

        # Step 2: Proportional coupon share for this item
        coupon_discount = Decimal(order.coupon_discount or 0)
        order_subtotal = Decimal(order.subtotal)  # subtotal after offer
        tax_total = order_subtotal * Decimal('0.18')

        if order_subtotal > 0:
            tax_share = (item_total / order_subtotal) * tax_total
        else:
            tax_share = Decimal('0.00')

        tax_share = tax_share.quantize(Decimal("0.01"))

        if order_total_price > 0:
            coupon_share = (item_total / order_total_price) * coupon_discount
        else:
            coupon_share = 0

        # Step 4: Final refund calculation
        refund_amount = item_total - coupon_share + delivery_refund+tax_share

        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        wallet.balance += refund_amount
        wallet.save()

        #  wallet transaction
        WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type='CREDIT',
            amount=refund_amount,
            description=f"Refund for cancelled item "
        )
    update_order_status(order)

    return JsonResponse({'success': True, 'message': 'Item cancelled successfully.'})
def update_order_status(order):
    items = order.items.all()
    if all(i.status == 'Returned' for i in items):
        order.status = 'Returned'
    elif all(i.status == 'Cancelled' for i in items):
        order.status = 'Cancelled'
    elif any(i.status == 'Returned' for i in items):
        order.status = 'Partially Returned'
    elif any(i.status == 'Cancelled' for i in items):
        order.status = 'Partially Cancelled'
    elif all(i.status == 'Delivered' for i in items):
        order.status = 'Delivered'
    else:
        order.status = 'Processing'
    order.save()


@login_required
@transaction.atomic
def return_order(request, item_id):
    item = get_object_or_404(OrderItem, id=item_id, order__user=request.user)
    order = item.order

    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request'}, status=400)

    reason = request.POST.get('reason', '').strip()
    if not reason:
        return JsonResponse({'error': 'Return reason required.'}, status=400)

    if item.status != 'Delivered':
        return JsonResponse({'error': 'Only delivered items can be returned.'}, status=400)


    item.return_status = 'Pending'
    item.return_requested_at = timezone.now()
    item.save()


    # create return request
    ReturnRequest.objects.create(
        order=order,
        item=item,
        requested_by=request.user,
        reason=reason,
        refund_amount=item.final_price * item.quantity,
        status='PENDING'
    )
    # update order overall status
    update_order_status(order)

    OrderActionLog.objects.create(order=order, item=item, user=request.user, action='ReturnItem', reason=reason)

    return JsonResponse({'success': True, 'message': 'Return request submitted successfully.'})

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

def remove_coupon(request):
    """AJAX: Remove applied coupon & return updated totals."""
    if request.method == 'POST':

        # Remove coupon from session
        request.session.pop('applied_coupon', None)
        request.session.pop('discount', None)
        request.session.modified = True
        cart = Cart.objects.get(user=request.user)
        cart.coupon = None   # <--- VERY IMPORTANT
        cart.save()
        # Recalculate totals
        cart = Cart.objects.get(user=request.user)
        subtotal = cart.items_offer_total()
        delivery = cart.delivery_charge()
        tax_amount = subtotal * Decimal('0.18')
        tax_amount = tax_amount.quantize(Decimal("0.01"))
        discount = 0
        total = subtotal +tax_amount+ delivery

        return JsonResponse({
            'success': True,
            'message': 'Coupon removed successfully.',
            'subtotal': round(subtotal, 2),
            'delivery_charge': delivery,
            'discount': discount,
            'total': round(total, 2),
                        'tax_amount': float(tax_amount)
        })

    return JsonResponse({'error': 'Invalid request.'}, status=400)



@transaction.atomic
def cancel_order_itemold(request, order_id, item_id):
    item = get_object_or_404(OrderItem, id=item_id, order__user=request.user)
    order = get_object_or_404(Order, id=order_id, user=request.user)

    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request'}, status=400)

    reason = request.POST.get('reason', '').strip()
    if not reason:
        return JsonResponse({'error': 'Cancellation reason required.'}, status=400)

    if item.status not in ['Pending', 'Processing']:
        return JsonResponse({'error': 'This item cannot be cancelled.'}, status=400)

    total_items = order.items.count()
    active_items = order.items.exclude(status='Cancelled')

    product_total = Decimal(item.final_price) * item.quantity

    coupon_discount_share = Decimal('0.00')
    if order.coupon_discount:
        subtotal = sum([(i.final_price * i.quantity) for i in active_items])
        if subtotal > 0:
            coupon_discount_share = (product_total / subtotal) * Decimal(order.coupon_discount)

    # -Delivery charge handling ---
    delivery_charge_total = Decimal(order.delivery_charge())
    # Check if all items are being cancelled
    remaining_items = order.items.exclude(id=item.id).exclude(status='Cancelled').count()
    if remaining_items == 0:
        # If last item, refund full delivery charge
        delivery_share = delivery_charge_total
    else:
        
        delivery_share = delivery_charge_total / total_items

    # Calculate total refund ---
    refund_amount = (product_total - coupon_discount_share) + delivery_share

    # ---  Update item status and refunded amount ---
    item.cancelled = True
    item.status = 'Cancelled'
    item.refunded_amount = refund_amount
    item.save(update_fields=['cancelled', 'status', 'refunded_amount'])

    # -Restore stock ---
    variant = item.variant
    variant.stock = (variant.stock or 0) + item.quantity
    variant.save(update_fields=['stock'])

    # ---  Log order action ---
    OrderActionLog.objects.create(
        order=order,
        item=item,
        user=request.user,
        action='CancelItem',
        reason=reason
    )

    # --- Wallet refund (for prepaid) ---
    if order.payment_method.lower() == 'razorpay':
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        wallet.balance += refund_amount
        wallet.save(update_fields=['balance', 'updated_at'])

        WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type='CREDIT',
            amount=refund_amount,
            description=f"Refund for cancelled item "
        )

    # --- Step 9: Update order refunded total (optional) ---
    order.refunded_amount = (order.refunded_amount or Decimal('0.00')) + refund_amount
    order.save(update_fields=['refunded_amount'])

    # --- Step 10: Update order status dynamically ---
    update_order_status(order)

    return JsonResponse({
        'success': True,
        'message': 'Item cancelled successfully with refund including offers, coupon, and delivery.'
    })

@transaction.atomic
def verify_return_request(request, rr_id):
    """Admin verifies and processes individual return requests."""
    rr = get_object_or_404(ReturnRequest, id=rr_id)
    action = request.GET.get('action')

    if action == 'approve':
        if rr.status == 'Approved':
            messages.warning(request, "This return request is already processed.")
            return redirect('admin_return_requests')

        rr.status = 'Approved'
        rr.verified_by_id = request.user.id
        rr.save()

        user = rr.requested_by
        order_item = rr.order_item
        order = order_item.order

        #  refund
        # refund_amount = Decimal(order_item.final_price or 0) * Decimal(order_item.quantity or 1)

        total_items = order.items.count() or 1
        product_total = Decimal(order_item.final_price) * order_item.quantity
        print("product_total",product_total)

        # refund_amount = Decimal(item.final_price)
                # --- Equal split of coupon and delivery ---
        coupon_discount = Decimal(order.coupon_discount or 0)
        coupon_share = coupon_discount / total_items

        # delivery_charge_total = (order.delivery_charge() or 0)
        delivery_charge_total = order.delivery_charge or Decimal('0.00')
        # print("delivery_charge_total",delivery_charge_total)

        delivery_share = delivery_charge_total / total_items
        # print("delivey",delivery_share)
        # --- Final refund amount ---
        refund_amount = (product_total - coupon_share) + delivery_share

        # --- Wallet Handling ---
        wallet, _ = Wallet.objects.get_or_create(user=user)
        wallet.balance += refund_amount
        wallet.save()

        # --- Log Wallet Transaction ---
        WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type='CREDIT',
            amount=refund_amount,
            description=f"Refund for returned item "
        )

        # --- Update Order Item ---
        order_item.status = 'Returned'
        order_item.refunded_amount = refund_amount
        order_item.returned = True
        order_item.save()

        # --- Update Overall Order Status ---
        items = order.items.all()
        if all(i.status == 'Returned' for i in items):
            order.status = 'Returned'
        elif any(i.status == 'Returned' for i in items):
            order.status = 'Partially Returned'
        order.save()

        messages.success(
            request,
            f"Return approved — ₹{refund_amount:.2f} credited to {user.username}'s wallet."
        )

    elif action == 'reject':
        rr.status = 'Rejected'
        rr.verified_by_id = request.user.id
        rr.save()
        messages.warning(request, "Return request rejected.")

    else:
        messages.error(request, "Invalid action.")

    return redirect('admin_return_requests')


