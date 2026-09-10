# AI Handbook: Portfolio

Read this file before changing or publishing the project.

## Status

This personal project is a public-ready static portfolio with an optional
provider-free local contact service and an optional historical cloud reference
path. Content was refreshed from the NAS career briefings and targeted CV set
through 14 August 2026.

The public pages are:

- `index.html`
- `about.html`
- `experience.html`
- `projects.html`
- `contact.html`

## Claim Boundaries

- AWS employment is `Support Engineer Intern - Deployment`, March-August 2026.
- AWS claims cover structured training, hands-on scenarios, troubleshooting,
  service configuration, Amazon Q knowledge, and repeatable infrastructure
  concepts. Do not invent customer cases or production ownership.
- Evolumia's supported metrics are more than 20 server/NAS systems maintained
  and a 30% downtime reduction through proactive health checks and automation.
- Outlier AI work covers model-output evaluation and structured feedback.
- King of Meal Prep, recsbot, Taste Platform, Home Server NAS Platform, and
  this portfolio are personal work.
- Tensei, SafeZone, Project ARIA, and the IoT Traffic Control System must retain
  explicit group attribution.
- SafeZone is a high-level public narrative only. Never add its source,
  screenshots, internal identifiers, live endpoints, or internal artifacts.
- Tensei and Project ARIA repositories remain private pending rights approval.
- A prototype is not a production service. Do not invent adoption, accuracy,
  latency, cost, availability, customer, or business-impact metrics.
- Training and exam preparation are not earned certifications.

## Visual Assets

`assets/king-meal-prep.png` and `assets/recsbot-interface.png` were captured
from isolated local copies of the sanitized personal projects. Both used fresh
databases and synthetic content. They may be published with this portfolio.

Do not replace them with screenshots from private NAS runtimes or real user
data. Do not add screenshots from SafeZone, Tensei, Project ARIA, customer
systems, cloud consoles, or employer-managed tools.

Lucide 0.468.0 is bundled at `assets/lucide.min.js` under the ISC license.

## Contact Modes

Static hosting leaves `window.PORTFOLIO_CONTACT_ENDPOINT` empty. Valid form
submissions open a prefilled email draft; no data is posted.

`local_server.py` serves the same files and dynamically returns
`/api/contact` from `contact-config.js`. It validates, rate-limits, and stores
submissions in private SQLite storage outside the document root.

Never commit contact submissions, runtime databases, deployment logs, or
visitor data. A public backend must not be claimed as live unless its actual
deployment and end-to-end flow have been verified.

## Verification

Run:

```bash
make check
python3 local_server.py
```

Then verify desktop and mobile layouts, active navigation, menu keyboard
behavior, project filters, full-size screenshots, static email fallback, local
contact submission, focus visibility, reduced motion, the browser console, and
that no phone number or CV download is published.

## Publication

Run working-tree and history secret scans before publication. Publish only the
sanitized `main` branch. Keep deployment state, credentials, contact data,
private career documents, and generated archives out of Git.

Cloudflare Workers Static Assets, deployed by Workers Builds from `main`, is
the approved public architecture. `wrangler.jsonc` must keep
`assets.directory` pointed at the output of `scripts/build-cloudflare-pages.sh`;
never point it at the repository root. Do not add a Worker script, Pages
Functions, or a public API, and do not add a telephone number or downloadable
CV to a public export.

Cloudflare login, the GitHub connection, and custom domains require the
operator. Keep Wrangler and API credentials out of this repository, its build
variables, and any deployment bundle.

Host-specific operations, such as retiring an earlier self-hosted route, live
in the operator's private runbook and not in this repository. Cloudflare
publication does not authorize changing or deleting legacy AWS resources.
