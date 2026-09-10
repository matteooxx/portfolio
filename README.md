# Portfolio

Matteo Mastore's static multi-page portfolio, refreshed from evidence-backed
career briefings and canonical CV facts on 11 September 2026.

The site covers:

- solutions architecture, solutions engineering, cloud, platform, and
  AI-assisted engineering positioning;
- AWS, infrastructure-maintenance, and AI-review experience;
- personal projects with first-person ownership and public source links;
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

The public site runs on Cloudflare Workers Static Assets and is deployed by
Workers Builds from the `main` branch of this repository. Each build runs
`bash scripts/build-cloudflare-pages.sh`, which copies only the explicit static
allowlist and `cloudflare/_headers` into `dist/cloudflare-pages/`;
`wrangler.jsonc` publishes that directory and nothing else. The contact form
stays in mailto mode, and the site does not expose the NAS or require AWS.

```bash
make check
make cloudflare-build
```

`make cloudflare-build` reproduces the published tree locally. Cloudflare
account login, the GitHub connection, and custom domains are operator steps in
the Cloudflare dashboard. Validate every page, asset, security header, and the
contact fallback on the `*.workers.dev` hostname before routing a custom domain
to it. `make cloudflare-bundle` still produces a ZIP for a manual upload if one
is ever needed.

The optional historical AWS reference path remains in `infra/`, `lambda/`, and
`scripts/deploy.sh`; it is not used by the Cloudflare deployment.

## License

Source code is available under the [MIT License](LICENSE). Biography,
employment history, and project images are covered by [NOTICE.md](NOTICE.md).
Bundled third-party notices are in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
