FROM node:22-slim AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --no-fund --no-audit
COPY tsconfig.json ./
COPY src/ ./src/
RUN npx tsc

FROM node:22-slim
WORKDIR /app
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
COPY package.json ./
COPY ui/ ./ui/
COPY data/instructions/ ./data/instructions/
EXPOSE 8420
CMD ["node", "dist/index.js"]
