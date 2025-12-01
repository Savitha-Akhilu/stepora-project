def get_variant_image(variant):
    primary = variant.images.filter(is_primary=True).first()
    if primary:
        return primary.image.url

    first = variant.images.first()
    return first.image.url if first else None
