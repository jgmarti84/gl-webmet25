# frontend/Dockerfile
FROM nginx:alpine

# Copy nginx configuration (path relative to build context which is project root)
COPY frontend/nginx.conf /etc/nginx/nginx.conf

# Copy static files
COPY frontend/public/ /usr/share/nginx/html/

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]