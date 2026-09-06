# Vossome Window Cleaning

Client-facing build for Vossome Window Cleaning, a family-owned St. Charles window cleaning
and pressure washing company run by Matt Voss. The public experience uses the Vossome visual
system: Lato body copy, comic-book Bebas Neue display type, and the blue/green/orange energy
of the supplied brand assets. Content remains editable through the existing Django admin.

## Vossome frontend notes

- Authentic artwork is in `static/images/` and the visible header mark is `logo.jpg`.
- The home, services, service detail, about, FAQ, and contact templates all include useful
  Vossome-specific fallbacks when records have not yet been entered in admin.
- Leads continue to use the existing `LeadForm` and are stored in Django admin; no backend
  workflow or URL behavior was changed.
- Primary service areas are St. Charles and nearby St. Louis communities. The public phone
  number is `(314) 775-1080`.

A reusable, backend-first Django foundation for independently hosted client websites.
Each client receives its own GitHub repository, PostgreSQL database, DigitalOcean App,
environment configuration, and content records.

This template is intentionally vendor- and client-agnostic. An existing client project may
be consulted for reusable patterns, but its code, database, media, domains, account IDs,
credentials, analytics identifiers, and service configuration must never be copied here.

## What is included

- Environment-specific settings for local development, client review, builds, and production
- Django admin-managed site identity, pages, services, leads, and downloadable files
- SEO fields, sitemap, robots.txt, and a production health endpoint
- PostgreSQL support through `DATABASE_URL`
- WhiteNoise static-file serving
- Optional DigitalOcean Spaces media storage
- Docker and DigitalOcean App Platform examples
- GitHub Actions checks
- Idempotent environment-driven admin provisioning
- Google administrator SSO restricted to pre-existing allowlisted staff users
- Rate-limited emergency login with Argon2 hashing and 14-character password minimum
- Deliberately neutral templates that can be replaced per client

## Local setup

```bash
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000
```

Replit does not require a virtual environment. Run:

```bash
# From the repository root:
python manage.py migrate
python manage.py runserver 0.0.0.0:${PORT:-8000}
```

Then create one **Site settings** record at the configured admin URL.

## Start a new client project

1. Keep this repository free of client branding and mark it as a **Template repository**
   in GitHub settings.
2. Select **Use this template** and create a new private repository for the client.
3. Follow `FRONTEND_IMPLEMENTATION_GUIDE.md` to replace the README title and neutral
   front-end files in `templates/` and `static/`.
4. Copy `.env.example` to `.env` locally. Never commit `.env`.
5. Run migrations and create the first admin.
6. Enter identity, contact, legal, analytics, pages, and services in Django admin.
7. Follow `PREVIEW_SETUP.md` to share and revise the site before launch integrations exist.
8. When preparing to go live, copy `.do/app.yaml.example` to `.do/app.yaml`, replace every
   placeholder, and commit it.
9. Create a DigitalOcean PostgreSQL database and inject its private `DATABASE_URL`.
10. If editors upload files, create a Spaces bucket and configure the `AWS_*` variables.
11. Import the repository into DigitalOcean App Platform and verify the first deployment
    before enabling normal deploy-on-push.
12. Complete `CLIENT_SETUP_CHECKLIST.md` before launch.

## Pre-launch client review

Use `config.settings.preview` while collaborating with the client before the final domain
and integrated services are ready. Preview mode supports local admin access, database-backed
contact leads, and local media without requiring SMTP, Google OAuth, Spaces, analytics,
webhooks, or PostgreSQL.

See `PREVIEW_SETUP.md` for the Replit settings, run command, persistence limitations, and
the exact transition to production. Do not use the strict production settings for this
stage: their missing-integration failures are intentional launch safeguards.

## Frontend implementation

`FRONTEND_IMPLEMENTATION_GUIDE.md` is the frontend handoff for each client build. It maps the
Django templates and context variables, defines responsive and accessibility expectations,
covers SEO, assets, performance, and third-party scripts, and includes a frontend completion
checklist. Use it before replacing the neutral starter design.

## Production variables

Required:

- `DJANGO_SETTINGS_MODULE=config.settings.production`
- `SECRET_KEY`
- `DATABASE_URL`
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- `SITE_URL`

Recommended:

- `REQUIRE_POSTGRES=true`
- SMTP email variables
- DigitalOcean Spaces variables when uploads are enabled
- `SECURE_HSTS_SECONDS=3600` initially; raise after HTTPS is confirmed

The console email backend is preview-only. Contact submissions are always saved as Leads,
but production email delivery must be configured and tested before launch.

## External services

External-service configuration belongs to the client project, not this template. Every new
site must receive new provider resources and identifiers:

- A new Postmark server or equivalent email connection and sender-domain verification
- New Google Analytics, Tag Manager, Search Console, Maps, and reCAPTCHA identifiers as used
- A new DigitalOcean App, PostgreSQL database, Spaces bucket, and scoped access credentials
- New OAuth applications, webhook secrets, callback URLs, and API keys for any added service

Do not copy a previous client's `.env`, DigitalOcean app specification, database dump,
media bucket, OAuth application, or provider dashboard settings. Start from `.env.example`
and fill only the values issued for the new client. See `CLIENT_SETUP_CHECKLIST.md`.

## Hardened administrator login

Normal administrator access can use Google OAuth while Django continues to own staff status,
groups, and permissions. Google login is deliberately limited to an explicit email allowlist
and an existing active Django staff user. OAuth never creates a new staff account.

For each client:

1. Create the administrator in Django with `is_staff` enabled.
2. Create a new Google OAuth **Web application** for that client.
3. Add this authorized redirect URI:
   `https://CLIENT-DOMAIN/accounts/google/login/callback/`
4. Set `ENABLE_GOOGLE_ADMIN_SSO=true`.
5. Store `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET` in the deployment secrets.
6. Set `ADMIN_GOOGLE_ALLOWED_EMAILS` to a comma-separated list of approved staff emails.
7. Set unique `ADMIN_URL` and `ADMIN_LOCAL_LOGIN_URL` paths for the client.
8. Require two-step verification on every approved Google account.

The normal admin login URL redirects to Google when SSO is enabled. The separately configured
local login URL is reserved for the break-glass superuser. It is protected by five-attempt
lockout, a 30-minute cooldown, Argon2 password hashing, and the 14-character password policy.
Store that account's long random password in a password manager and deployment secret storage.

Changing the admin URL reduces automated scanner noise, but it is not the primary security
control. The allowlist, existing-staff requirement, MFA, lockout, and emergency-account
discipline provide the meaningful protection.

## Production commands

- Build: the Dockerfile installs dependencies and collects static files.
- Pre-deploy: `python manage.py migrate --noinput`
- Run: Gunicorn is defined by the Dockerfile.
- Health check: `/healthz/`

For Replit publishing, the workspace `.replit` file also declares explicit build and
Gunicorn run commands. It defaults to preview settings until
`DJANGO_SETTINGS_MODULE=config.settings.production` and the required production
database/domain secrets are configured.

Do not run migrations in every web process. The provided App Platform example uses a
single pre-deploy job so multiple web instances cannot race.

## Admin provisioning

For automation, set all three values temporarily:

- `DJANGO_SUPERUSER_USERNAME`
- `DJANGO_SUPERUSER_EMAIL`
- `DJANGO_SUPERUSER_PASSWORD`

Then run:

```bash
python manage.py provision_admin
```

Remove the password variable afterward. Existing users are not modified.

## Template maintenance

Treat this repository as a product with tagged releases. Client repositories should not
automatically pull template changes. Review and selectively port security fixes or new
features into each client project so client-specific code is never overwritten.

The original reference project remains independent. Template work must not edit, push to,
deploy, or migrate that project's repository or infrastructure.
