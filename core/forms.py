import re

from django import forms

from .models import Lead
from .quote_fields import QuoteFields
from .pricing import QUOTE_FIELDS, SERVICE_FIELDS, estimate_quote


class LeadForm(QuoteFields, forms.ModelForm):
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
            "service_address",
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
            "service_address": "Service address",
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
        self.fields["phone"].required = False
        self.fields["email"].required = False
        self.fields["message"].required = False
        self.fields.pop("selected_services")
        self.fields["preferred_reply_method"].required = True
        self.fields["preferred_reply_method"].choices = [
            *Lead.ReplyMethod.choices
        ]
        self.fields["deck_material"].choices = [
            ("", "Please choose"), ("composite", "Composite"), ("wood", "Wood"),
            ("other", "Other"), ("unsure", "I’m not sure"),
        ]
        self.fields["deck_material"].required = False
        self.fields["service_address"].widget = forms.Textarea(attrs={"rows": 3, "autocomplete": "street-address"})
        # Ignore stale/hostile measurements for services the visitor deselected.
        if self.is_bound:
            selected = set(self.data.getlist("services") if hasattr(self.data, "getlist") else self.data.get("services", []))
            if not selected and self.data.get("service_interest"):
                selected.add(self.data["service_interest"])
            for service, names in SERVICE_FIELDS.items():
                if service not in selected:
                    for name in names:
                        self.fields[name].disabled = True
            for unknown, names in {
                "window_unknown": ("window_count",),
                "gutter_unknown": ("gutter_one", "gutter_one_half", "gutter_two", "gutter_three"),
                "surface_unknown": ("surface_area", "surface_length", "surface_width"),
                "deck_unknown": ("deck_area", "deck_railing"),
            }.items():
                if self.data.get(unknown):
                    for name in names:
                        self.fields[name].disabled = True

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
        if "deck-cleaning" not in cleaned.get("services", []):
            cleaned["deck_material"] = ""
        method = cleaned.get("preferred_reply_method")
        if method in ("text", "call") and not cleaned.get("phone"):
            self.add_error("phone", "Enter a phone number so the team can call or text you.")
        if method == "email" and not cleaned.get("email"):
            self.add_error("email", "Enter an email address so the team can reply.")
        self.estimated_quote = estimate_quote(cleaned.get("services", []), cleaned)
        return cleaned

    def save(self, commit=True):
        lead = super().save(commit=False)
        lead.selected_services = self.cleaned_data["services"]
        lead.deck_material = self.cleaned_data["deck_material"]
        active_fields = {name for service in lead.selected_services for name in SERVICE_FIELDS.get(service, ())}
        lead.quote_details = {
            key: str(value) if key in QUOTE_FIELDS and hasattr(value, "as_tuple") else value
            for key, value in self.cleaned_data.items() if key in active_fields
        }
        lead.estimate_snapshot = estimate_quote(lead.selected_services, lead.quote_details)
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
        if not raw_phone:
            return ""
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
