from .models import Cart

def cart_count(request):
    """
    Makes the user's cart count globally available to all templates.
    Works for both logged-in and guest (session-based) users.
    """
    #  Logged-in user
    if request.user.is_authenticated:
        try:
            cart = Cart.objects.get(user=request.user)
            total = sum(item.quantity for item in cart.items.all())
            return {'cart_count': total}
        except Cart.DoesNotExist:
            return {'cart_count': 0}

    #  Guest user (session-based cart)
    session_cart = request.session.get('cart', {})
    return {'cart_count': sum(item['quantity'] for item in session_cart.values())}
