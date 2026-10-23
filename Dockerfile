# Glama / container build: zero-dependency stdio proxy to the public
# Dead Brands Bot Arena endpoint (https://mcp.deadbrands.co/arena/mcp).
FROM node:20-alpine
WORKDIR /app
COPY server/proxy.mjs ./server/proxy.mjs
ENV NODE_ENV=production
ENTRYPOINT ["node", "server/proxy.mjs"]
