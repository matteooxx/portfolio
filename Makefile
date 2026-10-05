.PHONY: local check cloudflare-build clean

local:
	python3 local_server.py

check:
	node --check script.js
	node --check worker/index.mjs
	node --test tests/worker.test.mjs
	test -f assets/king-meal-prep.webp
	test -f assets/recsbot-interface.webp
	test -f assets/og-card.png
	test -f assets/fonts/plex-sans-400.woff2
	test -f assets/fonts/plex-mono-400.woff2
	python3 -m unittest discover -s tests

cloudflare-build:
	rm -rf dist/cloudflare-pages
	bash scripts/build-cloudflare-pages.sh

clean:
	rm -rf runtime dist
