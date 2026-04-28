# frontend/Dockerfile
# Unified frontend container for both v1 and v2.
#
# Build arguments:
#   FE_VERSION — which frontend to serve: v1 (default) or v2
#
# Usage:
#   docker compose build --build-arg FE_VERSION=v2 frontend
#   docker compose up -d frontend
#
# Or via .env file:
#   FE_VERSION=v2
#   docker compose up -d --build frontend

FROM nginx:alpine

ARG FE_VERSION=v1

# Copy all static files
COPY frontend/public/ /usr/share/nginx/html/

# Substitute the entry point script tag in index.html
RUN sed -i \
    "s|FE_ENTRY_POINT|js/${FE_VERSION}/app.js|g" \
    /usr/share/nginx/html/index.html

# Inject v2 badge or remove placeholder
RUN if [ "$FE_VERSION" = "v2" ]; then \
        sed -i 's|FE_V2_BADGE|<div id="v2-indicator" style="position:fixed;top:8px;left:8px;background:#e74c3c;color:white;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:bold;z-index:10000;pointer-events:none;">v2-canvas</div>|g' \
            /usr/share/nginx/html/index.html; \
    else \
        sed -i 's|FE_V2_BADGE||g' \
            /usr/share/nginx/html/index.html; \
    fi

# Copy unified nginx config
COPY frontend/nginx.conf /etc/nginx/nginx.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]