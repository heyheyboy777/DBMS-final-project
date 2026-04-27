from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserChangeForm

class UserProfileForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(), required=False, label="新密碼")
    password_confirm = forms.CharField(widget=forms.PasswordInput(), required=False, label="確認新密碼")

    class Meta:
        model = User
        fields = ['first_name', 'last_name']

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")

        if password and password != password_confirm:
            raise forms.ValidationError("密碼確認不匹配")

        return cleaned_data