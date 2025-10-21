from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Product, ProductImage,ProductVariant
from .forms import ProductForm
from adminpanel.models import  Gender,Brand,Category
from category.models import Color,Size,Occasion,Material
from django.db import transaction
@login_required

def product_list(request):
    total_products = Product.objects.count()
    active_products = Product.objects.filter(is_active=True).count()
    inactive_products = total_products - active_products
    products = Product.objects.all()

    context = {
        'total_products': total_products,
        'active_products': active_products,
        'inactive_products': inactive_products,
        'products': products
    }
    return render(request, 'products/product_list.html', context)
@login_required
def add_product(request):
    if not request.user.is_admin:
        return redirect('home')

    colors = Color.objects.all()
    sizes = Size.objects.all()
    materials = Material.objects.all()
    occasions = Occasion.objects.all()
    genders = Gender.objects.all()
    brands = Brand.objects.all()
    categories = Category.objects.all()

    if request.method == 'POST':
        product_form = ProductForm(request.POST)
        files = request.FILES.getlist('images')
        # print(request.POST)

        if product_form.is_valid():
            if len(files) < 3:
                messages.error(request, "Please upload at least 3 images")
            else:
                try:
                    with transaction.atomic():
                        # Save product
                        product = product_form.save(commit=False)
                        product.created_by = request.user
                        product.save()

                        # Save variants
                        variant_names = request.POST.getlist('variant_name[]')
                        skus = request.POST.getlist('sku[]')
                        stocks = request.POST.getlist('stock[]')
                        low_stock_qtys = request.POST.getlist('low_stock_qty[]')
                        colors_selected = request.POST.getlist('color[]')
                        sizes_selected = request.POST.getlist('size[]')
                        materials_selected = request.POST.getlist('material[]')
                        occasions_selected = request.POST.getlist('occasion[]')
                        discounts = request.POST.getlist('discount[]')
                        prices = request.POST.getlist('price[]')
                        short_description = request.POST.getlist('short_desc[]')
                        long_description = request.POST.getlist('long_desc[]')
                        # print(len(variant_names), len(skus), len(stocks), len(colors), len(sizes))
                        variants = []
                        for i in range(len(variant_names)):
                            variant = ProductVariant.objects.create(
                                product=product,
                                variant_name=variant_names[i],
                                sku=skus[i],
                                stock=int(stocks[i]),
                                low_stock_qty=int(low_stock_qtys[i]) if low_stock_qtys[i] else 0,
                                color_id=colors_selected[i],
                                size_id=sizes_selected[i],
                                material_id=materials_selected[i] if materials_selected[i] else None,
                                occasion_id=occasions_selected[i] if occasions_selected[i] else None,
                                discount=float(discounts[i]) if discounts[i] else 0,
                                price=float(prices[i]),
                                short_description=short_description[i],
                                long_description=long_description[i]
                            )
                            variants.append(variant)

                        # Save images
                        # You can make first variant as default if images > variants
                        primary_index = request.POST.get('primary_image_index', '0')  # send in template
                        for idx, f in enumerate(files):
                            variant_for_image = variants[idx] if idx < len(variants) else variants[0]
                            ProductImage.objects.create(
                                variant=variant_for_image,
                                image=f,
                                is_primary=(str(idx) == primary_index)
                            )

                    messages.success(request, "Product, variants, and images added successfully")
                    return redirect('products:product_list')

                except Exception as e:
                    # Print the full error to console for debugging
                    import traceback
                    traceback.print_exc()
                    messages.error(request, f"Error saving product: {e}")

        else:
            messages.error(request, "Please correct the errors below")

    else:
        product_form = ProductForm()

    context = {
        'product_form': product_form,
        'colors': colors,
        'sizes': sizes,
        'materials': materials,
        'occasions': occasions,
        'genders': genders,
        'brands': brands,
        'categories': categories,
    }

    return render(request, 'products/add_product.html', context)

# def add_product(request):
#     if not request.user.is_admin:
#         return redirect('home')
#     colors = Color.objects.all()
#     sizes = Size.objects.all()
#     materials = Material.objects.all()
#     occasions= Occasion.objects.all()
#     genders=Gender.objects.all()
#     brands=Brand.objects.all()
#     categories=Category.objects.all()

#     if request.method == 'POST':
#         product_form = ProductForm(request.POST)
#         files = request.FILES.getlist('image')

#         if product_form.is_valid():
#             if len(files) < 3:
#                 messages.error(request, "Please upload at least 3 images")
#             else:
#                 product = product_form.save(commit=False)
#                 product.created_by = request.user
#                 product.save()

#                 for f in files:
#                     ProductImage.objects.create(variant=None, image=f, product=product)  # adapt if variant exists

#                 messages.success(request, "Product added successfully")
#                 return redirect('products:product_list')
#     else:
#         product_form = ProductForm()
    
#     context = {
#         'product_form': product_form,
#         'colors': colors,
#         'sizes': sizes,
#         'materials': materials,
#         'occasions': occasions,
#         'genders': genders,
#         'brands': brands,
#         'categories': categories,
#     }

#     return render(request, 'products/add_product.html', context)

@login_required
def edit_product(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    variants = product.variants.all()
    images = ProductImage.objects.filter(variant__in=variants)

    if request.method == "POST":
        product_form = ProductForm(request.POST, instance=product)
        if product_form.is_valid():
            product = product_form.save(commit=False)
            product.created_by = request.user
            product.save()

            # Clear old variants and recreate
            ProductVariant.objects.filter(product=product).delete()

            variant_names = request.POST.getlist('variant_name[]')
            skus = request.POST.getlist('sku[]')
            stocks = request.POST.getlist('stock[]')
            low_stock_qtys = request.POST.getlist('low_stock_qty[]')
            colors_selected = request.POST.getlist('color[]')
            sizes_selected = request.POST.getlist('size[]')
            materials_selected = request.POST.getlist('material[]')
            occasions_selected = request.POST.getlist('occasion[]')
            discounts = request.POST.getlist('discount[]')
            prices = request.POST.getlist('price[]')
            short_descs = request.POST.getlist('short_desc[]')
            long_descs = request.POST.getlist('long_desc[]')

            variants = []
            for i in range(len(variant_names)):
                v = ProductVariant.objects.create(
                    product=product,
                    name=variant_names[i],
                    sku=skus[i],
                    stock=stocks[i],
                    low_stock_qty=low_stock_qtys[i] or 0,
                    color_id=colors_selected[i] if colors_selected[i] else None,
                    size_id=sizes_selected[i] if sizes_selected[i] else None,
                    material_id=materials_selected[i] if materials_selected[i] else None,
                    occasion_id=occasions_selected[i] if occasions_selected[i] else None,
                    discount=discounts[i] or 0,
                    price=prices[i],
                    short_desc=short_descs[i],
                    long_desc=long_descs[i]
                )
                variants.append(v)

            # Handle images (optional: you can clear old images or keep)
            # Example: images cleared and re-uploaded
            files = request.FILES.getlist('images')
            primary_index = int(request.POST.get('primary_image_index', 0))
            for idx, f in enumerate(files):
                variant_for_image = variants[idx] if idx < len(variants) else variants[0]
                ProductImage.objects.create(
                    variant=variant_for_image,
                    image=f,
                    is_primary=(idx == primary_index)
                )

            return redirect('products:product_list')
    else:
        product_form = ProductForm(instance=product)

    context = {
        'product_form': product_form,
        'product': product,
        'variants': variants,
        'images': images,
        'categories': Category.objects.all(),
        'brands': Brand.objects.all(),
        'genders': Gender.objects.all(),
        'colors': Color.objects.all(),
        'sizes': Size.objects.all(),
        'materials': Material.objects.all(),
        'occasions': Occasion.objects.all(),
    }
    return render(request, 'products/edit_product.html', context)

@login_required
def delete_product(request, pk):
    if not request.user.is_admin:
        return redirect('home')
    
    product = get_object_or_404(Product, pk=pk)
    product.is_active = False  # soft delete
    product.save()
    messages.success(request, "Product soft deleted successfully")
    return redirect('products:product_list')
