from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm


class CustomRegisterForm(UserCreationForm):
    first_name = forms.CharField(
        max_length=30,
        required=True,
        label="Имя",
        widget=forms.TextInput(attrs={'placeholder': 'Введите ваше имя'})
    )
    company_name = forms.CharField(
        max_length=100,
        required=False,
        label="Название компании",
        widget=forms.TextInput(attrs={'placeholder': 'ООО "Компания"'})
    )
    email = forms.EmailField(
        required=True,
        label="Email",
        widget=forms.EmailInput(attrs={'placeholder': 'example@domain.com'})
    )

    class Meta(UserCreationForm.Meta):
        model = User
        # Добавляем нужные поля в стандартную форму Django
        fields = ('username', 'first_name', 'email', 'company_name')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data['first_name']
        user.email = self.cleaned_data['email']

        # Если в модели User нет отдельного поля company_name,
        # сохраним компанию в last_name или отдельный профиль:
        user.last_name = self.cleaned_data['company_name']

        if commit:
            user.save()
        return user