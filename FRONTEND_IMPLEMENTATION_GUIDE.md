# Frontend Implementation Guide

Use this guide when turning the neutral Django templates into a finished client website.
The backend models, routes, forms, and administration are reusable; the visual design and
client-facing content should be rebuilt for each client.

## 1. Start with approved client inputs

Before changing templates, collect:

- Approved logo files, brand colors, typography, and photography
- Sitemap and navigation labels
- Page copy, calls to action, contact details, and legal text
- Mobile and desktop design references
- Accessibility, privacy, analytics, and consent requirements

Use only assets the client owns or has licensed. Never copy another client's design files,
fonts, images, copy, analytics tags, contact information, or legal language.

## 2. Know where frontend work lives

- `templates/base.html` — document shell, metadata defaults, header, navigation, messages,
  footer, global scripts, and stylesheet links
- `templates/includes/header.html` and `templates/includes/footer.html` — universal site
  navigation and footer shared by every public page
- `templates/home.html` — homepage
- `templates/about.html` — required About us page, managed by the published `about` Page
- `templates/services.html` — required listing of all published services
- `templates/page_detail.html` — admin-managed general pages
- `templates/service_detail.html` — admin-managed service pages
- `templates/faq.html` — required listing of published admin-managed FAQs
- `templates/contact.html` — contact form and validation output
- `templates/security/locked_out.html` — login-throttling message
- `static/css/site.css` — neutral starter styles and design tokens
- `static/` — version-controlled CSS, JavaScript, icons, and small interface assets

Keep reusable layout pieces in Django template includes when the same markup appears more
than once. Keep client-editable copy in Django admin models rather than hardcoding it into
templates.

## 3. Preserve the backend contract

Frontend replacements must continue to use the existing Django context and URL helpers:

- `site_settings` provides the site name, contact information, metadata default, footer
  disclaimer, and analytics measurement ID.
- `navigation_pages` contains published pages selected for navigation.
- `Page` and `Service` expose `seo_title`, `seo_description`, and `get_absolute_url`.
- Contact forms must render Django validation errors, include `{% csrf_token %}`, and retain
  the honeypot field.
- The universal header and footer must retain links to Home, About us, Services, FAQ, and
  Contact us. Additional published navigation pages may be added around those required links.
- Internal links should use `{% url %}` or model `get_absolute_url`; static assets should use
  `{% static %}`.

Do not hardcode the production domain, admin path, storage URL, or deployment hostname into
HTML, CSS, or JavaScript.

## 4. Establish a small design system

Replace the neutral CSS variables with client-approved tokens for:

- Color roles: background, surface, text, muted text, borders, brand, accent, success, warning,
  and error
- Typography: display, heading, body, and utility styles
- Spacing, container widths, border radii, shadows, and motion
- Buttons, links, inputs, cards, notices, navigation, and content typography

Use semantic names such as `--color-text` and `--space-section`, not names tied to a specific
hex value. Keep component states consistent across every page.

## 5. Responsive behavior

Build mobile-first and check at minimum:

- 320–375 px phones
- 768 px tablets
- 1024–1440 px desktop screens
- 200% browser zoom

Navigation must remain operable without clipped links. Forms, cards, tables, media, headings,
and long URLs must not overflow. Avoid fixed heights for text-bearing components.

If JavaScript controls a mobile menu, the page must remain navigable when JavaScript fails,
and the trigger must expose its expanded state to assistive technology.

## 6. Accessibility requirements

Treat WCAG 2.2 AA as the default target:

- Use one descriptive `h1` and a logical heading order.
- Keep landmarks and semantic elements such as `header`, `nav`, `main`, and `footer`.
- Provide a visible keyboard focus style and a skip-to-content link.
- Ensure all controls work by keyboard and have accessible names.
- Associate form labels, help text, and errors with their fields.
- Add meaningful alternative text to informative images and empty alternative text to
  decorative images.
- Maintain sufficient text and interface contrast.
- Do not rely on color alone to communicate status.
- Respect `prefers-reduced-motion`.
- Avoid autoplaying media, flashing content, and unexpected focus changes.

Test critical pages with only a keyboard and with automated accessibility tooling before
launch.

## 7. SEO and sharing

Each public page should provide:

- A unique title and meta description using the model SEO properties
- One canonical URL based on the configured `SITE_URL`
- Open Graph and social-sharing metadata using client-owned imagery
- Descriptive link text and meaningful heading structure

Preserve the existing sitemap and robots routes. Do not insert analytics, verification codes,
or third-party scripts directly into the master template. Configure fresh client-specific
identifiers and load scripts only when the client's consent requirements allow them.

Page and Service records automatically generate a search title, meta description, Open Graph
title, and Open Graph description from their title, summary, and body when an editor leaves
those fields blank. Editors should review and refine the generated text before publishing.
Each record can also receive its own Open Graph image; otherwise the site-wide image is used.

Published Page and Service bodies are validated at 650–900 words, targeting approximately
750 words of useful, original content. Do not add filler merely to satisfy the word count.

## 8. Images, fonts, and uploaded media

- Keep source design assets outside the public static directory unless they are intended to
  ship.
- Optimize raster images and provide explicit width and height to reduce layout shift.
- Prefer SVG for simple client-owned logos and icons.
- Use modern image formats when browser support and the editing workflow allow.
- Self-host fonts only when licensing permits; otherwise use an approved provider.
- Uploaded, editor-managed files belong in configured media storage, not `static/`.
- Never commit generated `staticfiles/` output.

## 9. Performance and resilience

- Keep initial CSS and JavaScript small; add libraries only when they provide clear value.
- Load non-critical scripts with `defer`.
- Lazy-load below-the-fold images and embeds.
- Avoid render-blocking third-party widgets.
- Provide useful empty, error, validation, and success states.
- Confirm pages remain understandable if fonts, images, analytics, or third-party embeds fail.

Run `collectstatic` and inspect the production build before launch.

## 10. Frontend completion checklist

- [ ] All neutral branding and placeholder copy have been replaced.
- [ ] No previous-client identifiers or assets remain.
- [ ] Navigation, footer, forms, messages, and error states match the approved design.
- [ ] Every page works at phone, tablet, desktop, and 200% zoom sizes.
- [ ] Keyboard navigation and visible focus states work.
- [ ] Heading order, labels, errors, alternative text, and contrast have been reviewed.
- [ ] Page titles, descriptions, canonical URLs, and social metadata are correct.
- [ ] Images and fonts are licensed, optimized, and loaded from the correct location.
- [ ] Consent-dependent scripts do not load before consent.
- [ ] No domain, admin path, credential, or provider identifier is hardcoded.
- [ ] Contact submission, downloads, 404/500 pages, and lockout messaging are styled and tested.
- [ ] `python manage.py check`, tests, and `collectstatic` pass.
- [ ] The deployed site has been reviewed on real mobile and desktop browsers.

## 11. Bringing master improvements into active clients

Do not overwrite a client's completed frontend with later master-template changes. Review
template updates file by file, port only the backend or security changes the client needs,
and adapt any HTML changes to that client's established components and design system.