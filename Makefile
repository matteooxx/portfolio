.PHONY: local check deploy invalidate smoke cloudflare-build cloudflare-bundle clean

deploy:
	bash scripts/deploy.sh

local:
	python3 local_server.py

check:
	node --check script.js
	node --check lambda/index.mjs
	node --check worker/index.mjs
	node --test tests/worker.test.mjs
	test -f assets/king-meal-prep.png
	test -f assets/recsbot-interface.png
	test -f assets/lucide.min.js
	python3 -m unittest discover -s tests

invalidate:
	@. ./.deploy-state.env && \
	INV=$$(aws cloudfront create-invalidation --distribution-id $$DIST_ID \
	  --paths "/*" --query 'Invalidation.Id' --output text) && \
	echo "Invalidation: $$INV" && \
	aws cloudfront wait invalidation-completed --distribution-id $$DIST_ID --id $$INV && \
	echo "completed"

smoke:
	bash scripts/smoke.sh

cloudflare-build:
	rm -rf dist/cloudflare-pages
	bash scripts/build-cloudflare-pages.sh

cloudflare-bundle:
	rm -rf dist/cloudflare-pages-ready
	bash scripts/package-cloudflare-pages.sh

clean:
	rm -rf runtime dist
