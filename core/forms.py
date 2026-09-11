from django import forms

from .models import Lead


class LeadForm(forms.ModelForm):
    website = forms.CharField(required=False, widget=forms.HiddenInput)
    service_interest = forms.ChoiceField(
        choices=[("", "Choose a service")] + list(Lead.ServiceInterest.choices),
        label="Service you’re interested in",
    )

    class Meta:
        model = Lead
        fields = [
            "first_name",
            "last_name",
            "email",
            "phone",
            "service_interest",
            "message",
            "consent_to_contact",
        ]
        labels = {
            "first_name": "First name",
            "last_name": "Last name",
            "phone": "Phone number",
            "message": "How can we help?",
            "consent_to_contact": "Vossome may contact me about this request.",
        }
        widgets = {
            "first_name": forms.TextInput(attrs={"autocomplete": "given-name"}),
            "last_name": forms.TextInput(attrs={"autocomplete": "family-name"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "phone": forms.TextInput(attrs={"autocomplete": "tel"}),
            "message": forms.Textarea(
                attrs={
                    "rows": 5,
                    "placeholder": "Tell us a little about your property and what needs attention.",
                }
            ),
        }

    def clean_website(self):
        value = self.cleaned_data.get("website")
        if value:
            raise forms.ValidationError("Unable to submit this form.")
        return value
