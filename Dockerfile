# Stage 1: Build frontend with webpack
FROM sharelatex/sharelatex AS builder

# Copy ResearchKit module and modified files
COPY services/web/modules/researchkit /overleaf/services/web/modules/researchkit
COPY services/web/config/settings.defaults.js /overleaf/services/web/config/settings.defaults.js
COPY services/web/app/src/infrastructure/mongodb.mjs /overleaf/services/web/app/src/infrastructure/mongodb.mjs

# Add 'researchkit' to the RailTabKey union in the production image path
RUN sed -i "s/| 'workbench'/| 'workbench'\n  | 'researchkit'/" \
    /overleaf/services/web/frontend/js/features/ide-redesign/contexts/rail-context.tsx

# Install dev dependencies (needed for webpack) and rebuild frontend
WORKDIR /overleaf/services/web
RUN npm install --include=dev && npx webpack --config webpack.config.prod.js

# Stage 2: Production image with rebuilt frontend
FROM sharelatex/sharelatex

# Install the full TeX Live scheme in the main app container so
# community-edition compiles don't require package-by-package maintenance.
# Retry with the matching frozen TeX Live repository if the default mirror is newer.
RUN tlmgr install scheme-full || ( \
      TL_YEAR="$(ls /usr/local/texlive | grep -E '^[0-9]{4}$' | sort -nr | head -n 1)" && \
      tlmgr option repository "https://ftp.math.utah.edu/pub/tex/historic/systems/texlive/${TL_YEAR}/tlnet-final" && \
      tlmgr install scheme-full \
    )

# Copy ResearchKit module and modified backend files
COPY services/web/modules/researchkit /overleaf/services/web/modules/researchkit
COPY services/web/config/settings.defaults.js /overleaf/services/web/config/settings.defaults.js
COPY services/web/app/src/infrastructure/mongodb.mjs /overleaf/services/web/app/src/infrastructure/mongodb.mjs

# Add 'researchkit' to the RailTabKey union
RUN sed -i "s/| 'workbench'/| 'workbench'\n  | 'researchkit'/" \
    /overleaf/services/web/frontend/js/features/ide-redesign/contexts/rail-context.tsx

# Copy rebuilt webpack bundles from builder
COPY --from=builder /overleaf/services/web/public /overleaf/services/web/public

# Add nginx SSE support for ResearchKit chat endpoint
RUN mkdir -p /etc/nginx/vhost-extras/overleaf && \
    echo 'location ~ ^/project/[0-9a-f]+/researchkit/chat$ { proxy_pass http://127.0.0.1:4000; proxy_http_version 1.1; proxy_set_header Host $host; proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; proxy_buffering off; proxy_cache off; proxy_read_timeout 300s; chunked_transfer_encoding off; }' \
    > /etc/nginx/vhost-extras/overleaf/researchkit-sse.conf
