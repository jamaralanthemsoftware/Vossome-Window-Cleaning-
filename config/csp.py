CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'self'",
        "base-uri 'self'",
        "object-src 'none'",
        "form-action 'self'",
        "frame-ancestors 'none'",
        (
            "script-src 'self' "
            "https://www.googletagmanager.com/gtag/js "
            "https://www.google.com/recaptcha/ "
            "https://www.gstatic.com/recaptcha/"
        ),
        (
            "connect-src 'self' "
            "https://www.google-analytics.com/g/collect "
            "https://region1.google-analytics.com/g/collect "
            "https://www.google.com/recaptcha/"
        ),
        (
            "frame-src "
            "https://www.google.com/maps/ "
            "https://www.google.com/recaptcha/ "
            "https://recaptcha.google.com/recaptcha/"
        ),
        "img-src 'self' data:",
        "font-src 'self' https://fonts.gstatic.com",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "manifest-src 'self'",
        "media-src 'self'",
        "worker-src 'self' blob:",
        "upgrade-insecure-requests",
    )
)