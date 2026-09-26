import re

from django import forms

from .models import Lead


class LeadForm(forms.ModelForm):
    website = forms.CharField(required=False, widget=forms.HiddenInput)
    submission_token = forms.UUIDField(widget=forms.HiddenInput)
    services = forms.MultipleChoiceField(
        choices=[
            ("window-cleaning", "Window cleaning"),
            ("pressure-washing", "House washing"),
            ("gutter-cleaning", "Gutter cleaning"),
            ("concrete-patio-cleaning", "Driveway, patio, or walkway cleaning"),
            ("deck-cleaning", "Deck cleaning (please include material)"),
            ("other", "A fifteenth-century gargoyle or something else?"),
        ],
        widget=forms.CheckboxSelectMultiple,
        label="What can we help with? Select all that apply.",
        required=False,
    )

    class Meta:
        model = Lead
        fields = [
            "first_name",
            "last_name",
            "email",
            "phone",
            "selected_services",
            "deck_material",
            "preferred_reply_method",
            "message",
            "consent_to_contact",
        ]
        labels = {
            "first_name": "First name",
            "last_name": "Last name",
            "phone": "Phone number",
            "message": "How can we help?",
            "preferred_reply_method": "How would you prefer us to reply?",
            "deck_material": "What is your deck made of?",
            "consent_to_contact": "Vossome may contact me about this request.",
        }
        widgets = {
            "first_name": forms.TextInput(attrs={"autocomplete": "given-name"}),
            "last_name": forms.TextInput(attrs={"autocomplete": "family-name"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "preferred_reply_method": forms.RadioSelect(
                choices=[("", "No preference")] + list(Lead.ReplyMethod.choices)
            ),
            "deck_material": forms.RadioSelect(
                choices=[("", "Not sure")] + [("composite", "Composite"), ("wood", "Wood")]
            ),
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
        self.fields.pop("selected_services")
        self.fields["preferred_reply_method"].required = False
        self.fields["preferred_reply_method"].choices = [
            ("", "No preference"), *Lead.ReplyMethod.choices
        ]
        self.fields["deck_material"].choices = [
            ("", "Not sure"), ("composite", "Composite"), ("wood", "Wood")
        ]

    def clean_services(self):
        services = self.cleaned_data["services"]
        # Accept older clients still posting the original single-service form.
        if not services and self.is_bound:
            legacy = self.data.get("service_interest", "")
            if legacy in dict(Lead.ServiceInterest.choices):
                services = [legacy]
        if not services:
            raise forms.ValidationError("Select at least one service.")
        return services

    def clean(self):
        cleaned = super().clean()
        if "deck-cleaning" in cleaned.get("services", []) and not cleaned.get("deck_material"):
            self.add_error("deck_material", "Please choose composite or wood so we can review your deck.")
        if "deck-cleaning" not in cleaned.get("services", []):
            cleaned["deck_material"] = ""
        return cleaned

    def save(self, commit=True):
        lead = super().save(commit=False)
        lead.selected_services = self.cleaned_data["services"]
        lead.deck_material = self.cleaned_data["deck_material"]
        lead.service_interest = next(
            (value for value in lead.selected_services if value in dict(Lead.ServiceInterest.choices)),
            "",
        )
        if commit:
            lead.save()
            self.save_m2m()
        return lead

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
