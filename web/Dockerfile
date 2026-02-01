# Frontend Dockerfile
FROM node:20-alpine AS builder

WORKDIR /app

# 複製 package 檔案
COPY package*.json ./

# 安裝依賴
RUN npm ci

# 複製原始碼
COPY . .

# 建置生產版本
RUN npm run build

# 生產階段 - 使用 nginx
FROM nginx:alpine

# 複製建置產物
COPY --from=builder /app/dist /usr/share/nginx/html

# 複製 nginx 設定
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
