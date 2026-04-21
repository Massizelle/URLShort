FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
ARG VITE_SHORTENER_URL
ARG VITE_ANALYTICS_URL
ENV VITE_SHORTENER_URL=$VITE_SHORTENER_URL
ENV VITE_ANALYTICS_URL=$VITE_ANALYTICS_URL
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
