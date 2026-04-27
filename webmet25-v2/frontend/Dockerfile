# webmet25-v2/frontend/Dockerfile
FROM nginx:alpine

# Copy nginx configuration.
# Build context is the project root (webmet25/), so paths are relative to that.
COPY webmet25-v2/frontend/nginx.conf /etc/nginx/nginx.conf

# Copy static files
COPY webmet25-v2/frontend/public/ /usr/share/nginx/html/

EXPOSE 8090

CMD ["nginx", "-g", "daemon off;"]
