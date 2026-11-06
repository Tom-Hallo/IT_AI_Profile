# Frontend IT Talent AI Profile — image cho môi trường PHÁT TRIỂN (Technical Blueprint, mục 3).
# Không dùng cho production: bản production (build tĩnh + web server) thuộc PBI sau.
#
# Build context: thư mục frontend/ (docker-compose.yml khai báo `build: ./frontend`).
# Lệnh chạy do Compose đặt: npm run dev -- --host 0.0.0.0 --port 5173
# Healthcheck do Compose khai báo: wget -q -O /dev/null http://127.0.0.1:5173/

FROM node:24-alpine

WORKDIR /app
RUN chown node:node /app

# Chạy bằng user không phải root.
USER node

# Cài dependency theo đúng package-lock.json (tái lập được giữa các máy).
# Bước này đứng trước COPY mã nguồn để Docker cache lại khi chỉ sửa code.
COPY --chown=node:node package.json package-lock.json ./
RUN npm ci

COPY --chown=node:node . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
