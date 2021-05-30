FROM nginx
COPY nginx.conf /etc/nginx/cginx.conf
COPY index.html 
