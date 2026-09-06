# New Client Setup Checklist

Use this checklist for every site created from the template. Store secrets only in Replit,
GitHub Actions, or DigitalOcean environment settings—never in Git.

## 1. Isolation

- [ ] Create a new client repository from the template.
- [ ] Confirm the reference project repository has not been modified.
- [ ] Start with a new database; do not clone another client's production database.
- [ ] Start with empty media storage; copy only assets the new client owns and approved.
- [ ] Search the repository for the previous client's name, domains, emails, phone numbers,
      legal text, analytics IDs, bucket names, and account IDs.

Suggested pre-launch searches:

```bash
rg -n -i "previous-client-name|previous-domain" .
rg -n "G-[A-Z0-9]+|GTM-[A-Z0-9]+|UA-[0-9-]+|[0-9]{10,}-[a-z0-9]+\\.apps\\.googleusercontent\\.com" .
rg -n "postmark|server[_-]?token|api[_-]?key|client[_-]?secret|webhook[_-]?secret" .
```

Review every result. Example variable names are acceptable; real values are not.

## 2. Pre-launch client review

- [ ] Follow `PREVIEW_SETUP.md` and use `config.settings.preview`.
- [ ] Set a new `SECRET_KEY` for the review environment.
- [ ] Set the exact temporary hostname in `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, and `SITE_URL`.
- [ ] Keep Google SSO, Spaces, analytics, webhooks, and real email delivery disabled until needed.
- [ ] Run migrations and create a local administrator.
- [ ] Confirm the client can view all public pages over the temporary HTTPS URL.
- [ ] Submit the contact form and confirm the new Lead appears in Django admin.
- [ ] Confirm local uploads render, or provision persistent storage before relying on them.
- [ ] If review content must survive deployment rebuilds, provision PostgreSQL before data entry.

SQLite, local media, and console email are preview conveniences, not production services.

## 3. Core production infrastructure

- [ ] Create a new DigitalOcean App connected to the new client repository.
- [ ] Create a new PostgreSQL database and use its private connection URL.
- [ ] Set a new Django `SECRET_KEY`.
- [ ] Set the client's `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, and `SITE_URL`.
- [ ] Create a new Spaces bucket and scoped access key if the site accepts uploads.
- [ ] Create a new admin account; remove the provisioning password after use.

## 4. Email

- [ ] Create a new Postmark server, or a separate equivalent provider connection.
- [ ] Verify the client's sending domain.
- [ ] Add that client's SMTP/API credential to the deployment environment.
- [ ] Configure new sender and error-reporting addresses.
- [ ] Send and receive a production test message.

Never reuse another client's Postmark server token, message stream, webhook secret, or
sender signature.

## 5. Administrator access

- [ ] Create a new Google OAuth web application for this client.
- [ ] Register the exact production `/accounts/google/login/callback/` redirect URI.
- [ ] Create each administrator manually in Django and grant only required staff permissions.
- [ ] Add each administrator email to `ADMIN_GOOGLE_ALLOWED_EMAILS`.
- [ ] Confirm two-step verification is enabled for every approved Google account.
- [ ] Generate unique `ADMIN_URL` and `ADMIN_LOCAL_LOGIN_URL` values.
- [ ] Store one long, random break-glass password in a password manager and deployment secrets.
- [ ] Confirm an unapproved Google account cannot sign in.
- [ ] Confirm the emergency account locks after repeated failures.

## 6. Google services

Create only the services the site needs, with new client-owned identifiers:

- [ ] Google Analytics property and web stream
- [ ] Google Tag Manager container
- [ ] Search Console property and verification value
- [ ] Google Maps project/key with domain and API restrictions
- [ ] reCAPTCHA site and secret keys
- [ ] OAuth client with exact production callback URLs, if sign-in is added

Give the client access to the appropriate Google property rather than hiding ownership in
another client's account.

## 7. Other integrations

For every added provider:

- [ ] Create a separate project, app, workspace, webhook, or scoped credential.
- [ ] Restrict credentials to the minimum permissions and allowed domains.
- [ ] Use new webhook signing secrets and callback URLs.
- [ ] Document who owns the provider account.
- [ ] Record renewal, billing, quota, and offboarding responsibility outside the codebase.
- [ ] Test failure handling without exposing credentials in logs.

## 8. Content and launch

- [ ] Complete `FRONTEND_IMPLEMENTATION_GUIDE.md` and its frontend completion checklist.
- [ ] Replace all neutral templates, metadata, legal copy, contact details, and assets.
- [ ] Publish the About us page, every offered Service, and the client's FAQ entries.
- [ ] Keep each published Page and Service near 750 words and review its generated search metadata.
- [ ] Assign a relevant Open Graph image and confirm social previews for every public page.
- [ ] Confirm the universal header and footer link to Home, About us, Services, FAQ, and Contact us.
- [ ] Populate Site Settings in Django admin.
- [ ] Confirm analytics and consent behavior matches the client's requirements.
- [ ] Run `python manage.py check --deploy` using production settings.
- [ ] Run migrations through the single pre-deploy job.
- [ ] Verify `/healthz/`, forms, email delivery, static files, and uploaded media.
- [ ] Enable deploy-on-push only after the first deployment succeeds.
