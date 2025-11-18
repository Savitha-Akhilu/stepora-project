from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Product, ProductImage,ProductVariant
from .forms import ProductForm
from category.models import Color,Size,Occasion,Material,Brand,Category,Gender
from django.db import transaction
from django.http import JsonResponse
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
    for cat in categories:
        cat.display_name = f"{cat.category_name} - {cat.gender}" if cat.gender else cat.category_name

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
                        selected_category_id = product_form.cleaned_data['category'].id
                        selected_category = Category.objects.get(id=selected_category_id)
                        product.product_type_id = selected_category.gender
                        product.created_by = request.user
                        product.material_id = request.POST.get('material')
                        product.occasion_id = request.POST.get('occasion')
                        product.save()

                        # Save variants
                        variant_names = request.POST.getlist('variant_name[]')
                        skus = request.POST.getlist('sku[]')
                        stocks = request.POST.getlist('stock[]')
                        low_stock_qtys = request.POST.getlist('low_stock_qty[]')
                        colors_selected = request.POST.getlist('color[]')
                        sizes_selected = request.POST.getlist('size[]')
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
    categories = Category.objects.all()
    for cat in categories:
        cat.display_name = f"{cat.category_name} - {cat.gender.name}" if cat.gender else cat.category_name

    if request.method == "POST":
        print(request.POST)

        product_form = ProductForm(request.POST, instance=product)
        if product_form.is_valid():
            product = product_form.save(commit=False)
            product.created_by = request.user
            product.material_id = request.POST.get('material')
            product.occasion_id = request.POST.get('occasion')

            product.save()

            # Clear old variants and recreate
            ProductVariant.objects.filter(product=product).delete()

            variant_names = request.POST.getlist('variant_name[]')
            skus = request.POST.getlist('sku[]')
            stocks = request.POST.getlist('stock[]')
            low_stock_qtys = request.POST.getlist('low_stock_qty[]')
            colors_selected = request.POST.getlist('color[]')
            sizes_selected = request.POST.getlist('size[]')
            discounts = request.POST.getlist('discount[]')
            prices = request.POST.getlist('price[]')
            short_descs = request.POST.getlist('short_desc[]')
            long_descs = request.POST.getlist('long_desc[]')

            variants = []
            for i in range(len(variant_names)):
                v = ProductVariant.objects.create(
                    product=product,
                    variant_name=variant_names[i],
                    sku=skus[i],
                    stock=stocks[i],
                    low_stock_qty=low_stock_qtys[i] or 0,
                    color_id=colors_selected[i] if colors_selected[i] else None,
                    size_id=sizes_selected[i] if sizes_selected[i] else None,
                    discount=discounts[i] or 0,
                    price=prices[i],
                    short_description=short_descs[i],
                    long_description=long_descs[i]
                )
                variants.append(v)

                 # Fetch all existing images for these variants
            existing_images = list(ProductImage.objects.filter(variant__in=variants))
            primary_image_index = request.POST.get('primary_image_index')
            images_to_delete = request.POST.getlist('delete_images[]')
            if images_to_delete:
                     ProductImage.objects.filter(id__in=images_to_delete).delete()
                     existing_images = [img for img in existing_images if str(img.id) not in images_to_delete]

            #  new uploads
            files = request.FILES.getlist('images')
            new_images = []
            if files:
                 for f in files:
                      img = ProductImage.objects.create(
                      variant=variants[0],  # or map dynamically if needed
                      image=f,
                      is_primary=False
                       )
                      new_images.append(img)

            all_images = existing_images + new_images

            if primary_image_index is not None:
                 try:
                    ProductImage.objects.filter(variant__in=variants).update(is_primary=False)
                    selected_image = all_images[int(primary_image_index)]
                    selected_image.is_primary = True
                    selected_image.save()
                 except (IndexError, ValueError):
                        pass
        return redirect('products:product_list')
    else:
        product_form = ProductForm(instance=product)

    context = {
        'product_form': product_form,
        'product': product,
        'variants': variants,
        'images': images,
        'categories': categories,
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
def get_sizes_by_category(request):
    category_id = request.GET.get('category_id')
    sizes = []

    if category_id:
        try:
            category = Category.objects.get(id=category_id)
            sizes = Size.objects.filter(gender=category.gender).values('id', 'name')
        except Category.DoesNotExist:
            pass

    return JsonResponse({'sizes': list(sizes)})

