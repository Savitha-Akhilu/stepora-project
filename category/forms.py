from django import forms
from .models import Category

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['category_name', 'gender', 'description', 'image', 'is_active']
        widgets = {
            'category_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter category name'}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'gender': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_category_name(self):
        name = self.cleaned_data['category_name'].strip()
        if Category.objects.filter(category_name__iexact=name, is_active=False).exists():
            raise forms.ValidationError("A category with this name already exists.")
        return name
