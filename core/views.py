from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET
from django.views.generic import DetailView

from .forms import LeadForm
from .models import FAQ, Page, Service


@require_GET
def healthz(request):
    return JsonResponse({"status": "ok"})


@require_GET
def robots_txt(request):
    lines = ["User-agent: *", "Allow: /", "Sitemap: /sitemap.xml"]
    return HttpResponse("\n".join(lines), content_type="text/plain")


def home(request):
    return render(
        request,
        "home.html",
        {"services": Service.objects.filter(is_published=True)[:6]},
    )


def about(request):
    page = Page.objects.filter(slug="about", is_published=True).first()
    return render(request, "about.html", {"page": page})


def services(request):
    return render(
        request,
        "services.html",
        {"services": Service.objects.filter(is_published=True)},
    )


def faq(request):
    return render(
        request,
        "faq.html",
        {"faqs": FAQ.objects.filter(is_published=True)},
    )


class PageDetailView(DetailView):
    model = Page
    template_name = "page_detail.html"

    def get_queryset(self):
        return Page.objects.filter(is_published=True)


class ServiceDetailView(DetailView):
    model = Service
    template_name = "service_detail.html"

    def get_queryset(self):
        return Service.objects.filter(is_published=True)


def contact(request):
    form = LeadForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        lead = form.save(commit=False)
        lead.source = request.POST.get("source", "website")[:120]
        lead.save()
        messages.success(request, "Thank you. Your message has been received.")
        request.session["contact_submitted"] = True
        return redirect("contact")
    return render(request, "contact.html", {"form": form, "contact_submitted": request.session.pop("contact_submitted", False)})
