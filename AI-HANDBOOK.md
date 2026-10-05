# AI Handbook: Portfolio

Read this file before changing or publishing the project.

## Status

This personal project is a public-ready static portfolio with an optional
provider-free local contact service. Content was refreshed from the NAS
career briefings, the canonical targeted-CV facts, and the LinkedIn audit
through 11 September 2026.

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
- Training and exam preparation are not earned certifications. Do not mention
  AWS certification preparation.
- The degree is the three-year NFQ Level 7 BSc in Computing Systems and
  Operations (Software Development and DevOps), completed in May 2026 and
  already awarded: write it as a degree held, never as pending, expected or
  conferring. October 2026 is only the date of the in-person ceremony and
  belongs on the site nowhere. Never call it an Honours
  degree. The AWS internship was its Stage 3 work placement. Availability to
  start immediately may be stated.
- The AWS internship ended in August 2026 and may be described as completed.
  Collaboration with EMEA and Americas teams is supported; formal on-call or
  incident ownership is not.
- IoT Traffic Control: Matteo owned the data and observability layer and the
  AKS deployment (Python image automation, Kustomize overlays, two cloud-only
  defect fixes). CI/CD and ArgoCD belonged to teammates. Never claim GitOps
  ownership or leading the infrastructure workstream.
- Do not list OpenAI APIs; the evidenced model integrations are Ollama and
  Bedrock concepts.
- Coursework skills come from the official DkIT module descriptors for the
  three completed stages (read on 11 September 2026). They belong in skills
  lists and the education section only, never in project or employment
  claims. The operator confirmed hands-on coursework use of Terraform,
  CloudWatch, EventBridge, SNS, CloudTrail, AWS Config, VPC Flow Logs, ELK,
  Fluentd, and Prometheus; other tools the descriptors name only as examples
  (such as Nmap, Scrapy, and boto3) stay off the site, and Stage 4 modules
  were not taken.
- Source links may point only to the public personal repositories
  `king-of-meal-prep`, `recsbot`, `taste-platform`, and `portfolio`. Never link
  group, private, or legacy repositories.

## Visual Assets

`assets/king-meal-prep.webp` and `assets/recsbot-interface.webp` were captured
from isolated local copies of the sanitized personal projects. Both used fresh
databases and synthetic content. They may be published with this portfolio.

Do not replace them with screenshots from private NAS runtimes or real user
data. Do not add screenshots from SafeZone, Tensei, Project ARIA, customer
systems, cloud consoles, or employer-managed tools.

`assets/og-card.png` is the 1200x630 link-preview card: a text-only design
with no screenshot or embedded metadata. Every page except `404.html` declares
it with a `canonical` link and `og:url` set to the clean URL
(`https://matteomastore.com/about`, not `about.html`), because Cloudflare
redirects `.html` URLs. `404.html` is `noindex` and has no own URL.

Each page must be one complete document. Editing a page in the GitHub web
editor once pasted a new copy above the old one, so `projects.html` and
`contact.html` rendered every section twice; `tests/test_static_site.py` now
fails on repeated document elements, IDs, or meta tags.

Icons are inlined as SVG in the pages, and the two menu icons live in
`script.js`; the Lucide runtime is not shipped. Their paths come from Lucide
0.468.0 (ISC), whose licence stays at `assets/LUCIDE-LICENSE.txt` and is
published with the site. Take new icons from that release and keep the same
`data-lucide` attribute, so the existing `svg` styling applies.

`robots.txt` and `sitemap.xml` are published; the sitemap lists the clean URL
of every page except `404.html`. Each indexable page carries one JSON-LD
block, identical across pages. `script-src` has no `'unsafe-inline'`, so that
block is allowed by the `sha256-` hash in `cloudflare/_headers`: change the
block and the hash must change with it. `tests/test_static_site.py` enforces
both, and no external script, font, or stylesheet may be added.

## Design System

The site is a specification sheet, not a landing page. `style.css` is the whole
system: no framework, no CSS build step, every value a token in `:root`.

Ground and ink: white paper (`--paper`), a light tint for wells and banded
rows (`--paper-2`), a blue-black ink in three weights (`--ink`, `--ink-2`,
`--ink-3`), two rule greys, and one deep blue accent (`--accent`) used only for
links, the current page and focus. No dark ground, no fluorescent accent, no
shadows, blurs or gradients - those read as a generated template.

Type: IBM Plex Sans for text and headings (400 and 600 only), IBM Plex Mono for
data - dates, counts, record labels, field names - always with
`font-variant-numeric: tabular-nums` so columns align. Both are self-hosted in
`assets/fonts/` under the OFL and subset to the characters the site uses, which
is why they are about 65 KB in total; regenerate with `fontTools.subset` if a
character is missing. Headings stay at document sizes: the largest is under
3rem. Never set a page in one giant display face.

Layout: a label column (`--label`) holds the section label, dates or record
type; the wide column holds the content. Rows are separated by rules, not
boxed into cards. The home page opens with a title block - identity on the
left, a ruled field list (location, status, degree, most recent role) on the
right - the same shape as `assets/og-card.png`. Ownership is structural: a
solid ink rule on personal work, a dashed grey rule on group work.

Motion: none beyond state feedback on hover and focus, all of it listed
property by property, never `transition: all`. `prefers-reduced-motion` is
honoured. A print stylesheet drops the chrome so the pages print as sheets.

Quality floor for any change: contrast at least 4.5:1 (currently 4.52 and
above), a visible focus ring, a layout that holds from 375px to 1920px,
`[hidden]` still beating the layout rules so the project filter works, and
Lighthouse at 100 for accessibility, best practices and SEO.

## Contact Modes

The public site posts the contact form to `/api/contact`, handled by the
Cloudflare Worker in `worker/index.mjs`. Only `/api/*` runs the Worker
(`run_worker_first`); every page and asset is still served statically. The
Worker accepts JSON from the `ALLOWED_ORIGINS` origin only, applies the same
field rules and limits as `local_server.py`, verifies a Cloudflare Turnstile
token (action `contact`, hostname in `TURNSTILE_HOSTNAMES`), and emails the
message through the `CONTACT_EMAIL` send_email binding, which can reach only
the single verified destination address. It stores nothing and logs no message
content or addresses.

`contact-config.js` keeps `window.PORTFOLIO_CONTACT_ENDPOINT = "/api/contact"`.
An empty value restores the mailto draft for a host without the Worker.

`local_server.py` serves the same files and handles `/api/contact` locally. It
validates, rate-limits, and stores submissions in private SQLite storage
outside the document root; it does not verify Turnstile.

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
behavior, project filters, full-size screenshots, one real contact message on
the live site, local contact submission, focus visibility, reduced motion, the browser console, and
that no phone number or CV download is published.

## Publication

Run working-tree and history secret scans before publication. Publish only the
sanitized `main` branch. Keep deployment state, credentials, contact data,
private career documents, and generated archives out of Git.

Cloudflare Workers Static Assets, deployed by Workers Builds from `main`, is
the approved public architecture. `wrangler.jsonc` must keep
`assets.directory` pointed at the output of `scripts/build-cloudflare-pages.sh`;
never point it at the repository root. The only server-side code is
`worker/index.mjs` behind `/api/*`: do not add other routes, storage, Pages
Functions, or third-party form services without the operator's approval, and
do not add a telephone number or downloadable CV to a public export.

The Turnstile secret lives only as the Worker secret `TURNSTILE_SECRET_KEY`.
Email Routing on the zone, the verified destination address, and the
Turnstile widget (Managed mode, hostname `matteomastore.com`, public sitekey in
`contact.html`) are operator-managed in the Cloudflare dashboard.

Cloudflare login, the GitHub connection, and custom domains require the
operator. Keep Wrangler and API credentials out of this repository, its build
variables, and any deployment bundle.

Host-specific operations, such as retiring an earlier self-hosted route, live
in the operator's private runbook and not in this repository. Cloudflare
publication does not authorize changing or deleting legacy AWS resources.
