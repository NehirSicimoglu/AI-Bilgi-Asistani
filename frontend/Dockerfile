# Geliştirme/demo imajı: Vite dev sunucusu çalıştırır.
# Bilinçli tercih — Vite `VITE_*` değişkenlerini production build'de derleme
# anında gömer; dev sunucusu ise çalışma anında okur. docker-compose frontend'e
# VITE_API_KEY'i runtime'da geçtiği için tek imaj farklı anahtarlarla kullanılabilir.
# Gerçek dağıtımda `npm run build` çıktısı statik olarak sunulmalıdır.
FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
