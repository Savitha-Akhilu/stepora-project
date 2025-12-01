from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Product, ProductImage,ProductVariant
from .forms import ProductForm
from category.models import Color,Size,Occasion,Material,Brand,Category,Gender
from django.db import transaction
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q

@login_required
def product_list(request):

    query = request.GET.get('q', '').strip()
    products = Product.objects.all().order_by('-id')
    if query:
        products = products.filter(
            Q(name__icontains=query) |
            Q(category__category_name__icontains=query) |
            Q(brand__name__icontains=query)
        )

    #  Product counts
    total_products = Product.objects.count()
    active_products = Product.objects.filter(is_active=True).count()
    inactive_products = total_products - active_products


    #  Backend Pagination (10 per page)
    paginator = Paginator(products, 10) 
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'total_products': total_products,
        'active_products': active_products,
        'inactive_products': inactive_products,
        'page_obj': page_obj,
                'query': query,
    }

    return render(request, 'products/product_list.html', context)
@login_required
def add_product1(request):
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
        print(request.POST)

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
                           # Handle images for this specific variant
                            files = request.FILES.getlist(f'variant_images_{i}[]')

                          # Enforce at least 3 images per variant
                            if not files or len(files) < 3:
                              messages.error(request, f"Variant {i+1} ('{variant_names[i]}') must have at least 3 images.")
                              product.delete()  # clean up partially saved product
                              return redirect('products:add_product')

                          # Optional: find “primary” image index if you plan to store one
                            primary_keys = [key for key in request.POST.keys() if key.startswith(f'primary_image_variant_')]
                            primary_index = 0
                            if primary_keys:
                               try:
                                    primary_index = int(primary_keys[0].split('_')[-1])
                               except (IndexError, ValueError):
                                     primary_index = 0

                          #  Save images for this variant
                            for idx, f in enumerate(files):
                                 ProductImage.objects.create(
                                     variant=variant,
                                      image=f,
                                       is_primary=(idx == primary_index)
                                         )

                        messages.success(request, "Product, variants, and images added successfully.")
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
    selected_gender = None
    if product.category and product.category.gender:
        selected_gender = product.category.gender

    if selected_gender:
        sizes = Size.objects.filter(gender=selected_gender)
    else:
        sizes = Size.objects.all()  

    if request.method == "POST":
        # print(request.POST)

        product_form = ProductForm(request.POST, instance=product)
        if product_form.is_valid():
            delete_ids = request.POST.getlist(f"delete_images[]")
            if delete_ids:
                ProductImage.objects.filter(id__in=delete_ids).delete()

            product = product_form.save(commit=False)
            product.created_by = request.user
            product.material_id = request.POST.get('material')
            product.occasion_id = request.POST.get('occasion')
            category_id = request.POST.get('category')
            if category_id:
                 product.category_id = category_id
                 category_obj = Category.objects.filter(id=category_id).first()
                 if category_obj and category_obj.gender:
                     product.product_type_id = category_obj.gender.id
            product.save()

            variant_names = request.POST.getlist("variant_name[]")
            skus = request.POST.getlist("sku[]")
            stocks = request.POST.getlist("stock[]")
            low_stock_qtys = request.POST.getlist("low_stock_qty[]")
            colors_selected = request.POST.getlist("color[]")
            sizes_selected = request.POST.getlist("size[]")
            discounts = request.POST.getlist("discount[]")
            prices = request.POST.getlist("price[]")
            short_descs = request.POST.getlist("short_desc[]")
            long_descs = request.POST.getlist("long_desc[]")

            # --- Update or Create variants ---
            new_variants = []
            for i, name in enumerate(variant_names):
                if i < len(variants):
                    v = variants[i]
                    v.variant_name = name
                    v.sku = skus[i]
                    v.stock = int(stocks[i] or 0)
                    v.low_stock_qty = int(low_stock_qtys[i] or 0)
                    v.color_id = colors_selected[i] if colors_selected[i] else None
                    v.size_id = sizes_selected[i] if sizes_selected[i] else None
                    v.discount = float(discounts[i] or 0)
                    v.price = float(prices[i] or 0)
                    v.short_description = short_descs[i]
                    v.long_description = long_descs[i]
                    v.save()
                else:
                    v = ProductVariant.objects.create(
                        product=product,
                        variant_name=name,
                        sku=skus[i],
                        stock=int(stocks[i] or 0),
                        low_stock_qty=int(low_stock_qtys[i] or 0),
                        color_id=colors_selected[i] if colors_selected[i] else None,
                        size_id=sizes_selected[i] if sizes_selected[i] else None,
                        discount=float(discounts[i] or 0),
                        price=float(prices[i] or 0),
                        short_description=short_descs[i],
                        long_description=long_descs[i],
                    )
                new_variants.append(v)                

                # delete_ids = request.POST.getlist(f"delete_images[]")
                # if delete_ids:
                #     ProductImage.objects.filter(id__in=delete_ids).delete()

                # files = request.FILES.getlist(f"variant_images_{i}[]")
                # if files:
                #     for f in files:
                #         ProductImage.objects.create(variant=v, image=f, is_primary=False)

                # files = request.FILES.getlist(f"variant_images_{i}[]")
                # primary_selected_index = request.POST.get(f"primary_image_variant_{i}")

                # if files:
                #     for j, f in enumerate(files):
                #         is_primary = (str(j) == str(primary_selected_index))
                #         ProductImage.objects.create(
                #         variant=v,
                #         image=f,
                #         is_primary=is_primary
                #        )
                # files = request.FILES.getlist(f"variant_images_{i}[]")
                # primary_selected_index = request.POST.get(f"primary_image_variant_{i}")

                # #  CASE 1: If new files uploaded
                # if files:
                #     imgs = ProductImage.objects.filter(variant=v)
                #     imgs.update(is_primary=False)

                #     for j, f in enumerate(files):
                #         is_primary = (str(j) == str(primary_selected_index))
                #         ProductImage.objects.create(
                #             variant=v,
                #             image=f,
                #             is_primary=is_primary
                #         )
                files = request.FILES.getlist(f"variant_images_{i}[]")
                primary_selected_index = request.POST.get(f"primary_image_variant_{i}")

                # CASE 1: If new files uploaded
                if files:
                    # remove primary flag for all existing variant images
                    imgs = ProductImage.objects.filter(variant=v)
                    imgs.update(is_primary=False)

                    for f in files:
                        # create the ProductImage first
                        created = ProductImage.objects.create(variant=v, image=f, is_primary=False)

                        # If primary_selected_index matches this uploaded file's name, mark it primary
                        # note: uploaded file object has name attribute
                        try:
                            if primary_selected_index and primary_selected_index == f.name:
                                created.is_primary = True
                                created.save()
                        except Exception:
                            # fallback - ignore
                            pass


                # CASE 2: Update primary image even if no new files uploaded
                else:
                    if primary_selected_index:
                        imgs = ProductImage.objects.filter(variant=v)

                        try:
                            # 1. Try image ID
                            primary_img = imgs.filter(id=primary_selected_index).first()

                            # 2. Try list index
                            if not primary_img and primary_selected_index.isdigit():
                                all_imgs = list(imgs)
                                idx = int(primary_selected_index)
                                if 0 <= idx < len(all_imgs):
                                    primary_img = all_imgs[idx]

                            # 3. Try matching filename (NEW uploads)
                            if not primary_img:
                                primary_img = imgs.filter(image__icontains=primary_selected_index).first()

                            # Only update if found
                            if primary_img:
                                imgs.update(is_primary=False)
                                primary_img.is_primary = True
                                primary_img.save()
                            else:
                                print("Primary not found → keeping old primary.")

                        except Exception as e:
                            print("Primary error:", e)

     
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
        'sizes':sizes,
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

        if product_form.is_valid():
            try:
                with transaction.atomic():
                    # Save product
                    product = product_form.save(commit=False)
                    selected_category_id = product_form.cleaned_data['category'].id
                    selected_category = Category.objects.get(id=selected_category_id)
                    product.product_type_id = selected_category.gender.id
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
                    short_descs = request.POST.getlist('short_desc[]')
                    long_descs = request.POST.getlist('long_desc[]')

                    variants = []

                    for i in range(len(variant_names)):

                        variant = ProductVariant.objects.create(
                            product=product,
                            variant_name=variant_names[i],
                            sku=skus[i],
                            stock=int(stocks[i]) if stocks[i] else 0,
                            low_stock_qty=int(low_stock_qtys[i]) if low_stock_qtys[i] else 0,
                            color_id=colors_selected[i] if colors_selected[i] else None,
                            size_id=sizes_selected[i] if sizes_selected[i] else None,
                            discount=float(discounts[i]) if discounts[i] else 0,
                            price=float(prices[i]) if prices[i] else 0,
                            short_description=short_descs[i],
                            long_description=long_descs[i]
                        )
                        variants.append(variant)

                        files = request.FILES.getlist(f'variant_images_{i}[]')

                        #  at least 3 images per variant
                        if not files or len(files) < 3:
                            messages.error(request, f"Variant {i+1} ('{variant_names[i]}') must have at least 3 images.")
                            product.delete()
                            return redirect('products:add_product')

                        variant_primary_keys = [key for key in request.POST.keys()
                        if key.startswith(f'primary_image_variant_{i}_')]
                        primary_index = 0
                        # if primary_keys:
                        #     try:
                        #         primary_index = int(primary_keys[0].split('_')[-1])
                        #     except (IndexError, ValueError):
                        #         primary_index = 0

                        # #  Save images for this variant
                        # for idx, f in enumerate(files):
                        #     ProductImage.objects.create(
                        #         variant=variant,
                        #         image=f,
                        #         is_primary=(idx == primary_index)
                        #     )
                        primary_index = None
                        if variant_primary_keys:
                                try:
                                    # Extract last number: "primary_image_variant_1_2" → 2
                                    primary_index = int(variant_primary_keys[0].split('_')[-1])
                                except (IndexError, ValueError):
                                    primary_index = None

                            # ---- Save images ----
                        for idx, file in enumerate(files):
                                ProductImage.objects.create(
                                    variant=variant,
                                    image=file,
                                    is_primary=(primary_index is not None and idx == primary_index),
                                )

                    messages.success(request, "Product, variants, and images added successfully.")
                    return redirect('products:product_list')

            except Exception as e:
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

