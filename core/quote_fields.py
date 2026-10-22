"""Optional measurement inputs and verified, size-limited customer photos."""
import warnings
from io import BytesIO

from django import forms
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, ImageOps, UnidentifiedImageError


MAX_EMAIL_PHOTO_BYTES = 6 * 1024 * 1024


class MultiplePhotoInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class PhotosField(forms.FileField):
    widget = MultiplePhotoInput

    def clean(self, data, initial=None):
        files = data if isinstance(data, (tuple, list)) else ([data] if data else [])
        if len(files) > 5:
            raise forms.ValidationError("Please attach at most 5 photos.")
        validated = []
        for file in files:
            file = super().clean(file, initial)
            if file.size > 5 * 1024 * 1024:
                raise forms.ValidationError("Each photo must be 5 MB or smaller.")
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("error", Image.DecompressionBombWarning)
                    image = Image.open(file)
                    if image.format not in ("JPEG", "PNG", "WEBP"):
                        raise ValueError("Unsupported image")
                    if image.width * image.height > 25_000_000:
                        raise ValueError("Oversized image")
                    image.load()
                    image = ImageOps.exif_transpose(image).convert("RGB")
                    image.thumbnail((2400, 2400))
                    output = BytesIO()
                    image.save(output, format="JPEG", quality=85)
                    validated.append(SimpleUploadedFile("project-photo.jpg", output.getvalue(), content_type="image/jpeg"))
            except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
                raise forms.ValidationError("Please use a valid JPG, PNG, or WebP photo (up to 25 megapixels).")
        if sum(photo.size for photo in validated) > MAX_EMAIL_PHOTO_BYTES:
            raise forms.ValidationError("These photos are too large to email together after resizing. Please choose fewer photos.")
        return validated


def measurement(label):
    return forms.DecimalField(
        label=label, required=False, min_value=0, max_value=1_000_000,
        decimal_places=2, max_digits=9,
        widget=forms.NumberInput(attrs={"step": "0.01", "inputmode": "decimal"}),
    )


class QuoteFields(forms.Form):
    window_count = forms.IntegerField(label="How many windows are we talking?", required=False, min_value=0, max_value=100000)
    window_unknown = forms.BooleanField(label="I’m not sure", required=False)
    gutter_one = measurement("1-story gutters — approximate feet")
    gutter_one_half = measurement("1½-story gutters — approximate feet")
    gutter_two = measurement("2-story gutters — approximate feet")
    gutter_three = measurement("3-story gutters — approximate feet")
    gutter_unknown = forms.BooleanField(label="I’m not sure—please measure for me", required=False)
    house_three_stories = forms.ChoiceField(label="Is your home three stories tall?", required=False, choices=[("", "Please choose"), ("no", "No"), ("yes", "Yes"), ("unsure", "I’m not sure")])
    house_large = forms.ChoiceField(label="Is your home larger than 4,000 square feet?", required=False, choices=house_three_stories.choices)
    house_roof = forms.ChoiceField(label="Will we need to get on the roof?", required=False, choices=house_three_stories.choices)
    surface_area = measurement("Approximate surface area — square feet")
    surface_length = measurement("Or approximate length — feet")
    surface_width = measurement("Approximate width — feet")
    surface_unknown = forms.BooleanField(label="I’m not sure—please measure for me", required=False)
    deck_area = measurement("Deck walking surface — approximate square feet")
    deck_railing = measurement("Railing — approximate feet (enter 0 for none)")
    deck_unknown = forms.BooleanField(label="I’m not sure about the measurements", required=False)
    deck_stairs = forms.BooleanField(label="My deck has stairs — please review", required=False)
    deck_underside = forms.BooleanField(label="Interested in underside cleaning, too?", required=False)
    deck_access = forms.CharField(label="Anything we should know about access?", required=False, max_length=3000, widget=forms.Textarea(attrs={"rows": 3}))
    photos = PhotosField(label="Optional project photos", required=False, widget=MultiplePhotoInput(attrs={"accept": "image/jpeg,image/png,image/webp"}))
