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

# Copy unified nginx config
COPY frontend/nginx.conf /etc/nginx/nginx.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
