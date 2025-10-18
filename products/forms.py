from django import forms
from .models import Product

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            'name', 'category', 'brand', 'product_type', 'manufacture_details', 'is_active'
        ]
        widgets = {
            'manufacture_details': forms.Textarea(attrs={'rows':2, 'placeholder':'Manufacture details'}),
        }
