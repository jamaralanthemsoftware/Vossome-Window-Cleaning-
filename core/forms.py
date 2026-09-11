import re

from django import forms

from .models import Lead


class LeadForm(forms.ModelForm):
    website = forms.CharField(required=False, widget=forms.HiddenInput)
    submission_token = forms.UUIDField(widget=forms.HiddenInput)
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

    def __init__(self, *args, expected_submission_token=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.expected_submission_token = expected_submission_token
        self.fields["phone"].required = True

    def clean_phone(self):
        raw_phone = self.cleaned_data["phone"].strip()
        if not re.fullmatch(
            r"(?:\+?1[\s.\-]?)?(?:\([2-9]\d{2}\)|[2-9]\d{2})"
            r"[\s.\-]?[2-9]\d{2}[\s.\-]?\d{4}",
            raw_phone,
        ):
            raise forms.ValidationError(
                "Enter a valid 10-digit US phone number."
            )
        digits = re.sub(r"\D", "", raw_phone)
        if len(digits) == 11 and digits.startswith("1"):
            digits = digits[1:]
        return digits

    def clean_submission_token(self):
        value = self.cleaned_data["submission_token"]
        if not self.expected_submission_token or str(value) != str(
            self.expected_submission_token
        ):
            raise forms.ValidationError(
                "This form session has expired. Please refresh and try again."
            )
        return value

    def clean_website(self):
        value = self.cleaned_data.get("website")
        if value:
            raise forms.ValidationError("Unable to submit this form.")
        return value
