# Portfolio

Matteo Mastore's static multi-page portfolio, refreshed from evidence-backed
career briefings on 14 August 2026.

The site covers:

- cloud, platform, SRE, AI solutions, and solutions architecture positioning;
- AWS, infrastructure-maintenance, and AI-review experience;
- personal projects with first-person ownership;
- explicitly attributed internship, university, and group projects.

Project screenshots use disposable local databases and synthetic content. They
contain no household, conversation, customer, employer, or production data.

## Run Locally

For a static preview:

```bash
python3 -m http.server 8080
```

Open <http://127.0.0.1:8080>. The contact form opens a validated email draft
because `contact-config.js` has no endpoint.

For the optional same-origin local contact service:

```bash
python3 local_server.py
```

The service stores validated submissions in the ignored
`runtime/contacts.db`, applies per-client rate limits, and expires records
after 90 days by default.

## Structure

- `index.html`: homepage and featured work
- `about.html`: profile, skills, education, training, and languages
- `experience.html`: employment and applied engineering
- `projects.html`: filterable evidence-calibrated project inventory
- `contact.html`: contact details and form
- `404.html`: Cloudflare-compatible not-found response
- `assets/`: synthetic project previews and bundled Lucide runtime
- `local_server.py`: optional standard-library contact service
- `lambda/`, `infra/`, `scripts/deploy.sh`: optional cloud reference path

## Checks

```bash
make check
```

The checks cover JavaScript syntax, local contact validation/storage, static
page references, required claim boundaries, image dimensions, and the public
privacy boundary for phone and CV data.

## Deployment

Cloudflare Pages Direct Upload is the selected public-hosting path. It publishes
only an explicit static allowlist and leaves the contact form in mailto mode.
It does not expose the NAS or require AWS.

```bash
make cloudflare-build
make cloudflare-bundle
```

The second command creates a dashboard-ready ZIP under
`dist/cloudflare-pages-ready/`. Cloudflare account login and first project
creation are operator steps in the Cloudflare dashboard or with Wrangler;
`scripts/deploy-cloudflare-pages.sh` never starts OAuth or creates a project.
Validate every page, asset, security header, and the contact fallback on the
`*.pages.dev` hostname before routing any other domain to it.

The optional historical AWS reference path remains in `infra/`, `lambda/`, and
`scripts/deploy.sh`; it is not used by the Cloudflare deployment.

## License

Source code is available under the [MIT License](LICENSE). Biography,
employment history, and project images are covered by [NOTICE.md](NOTICE.md).
Bundled third-party notices are in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
