# Glama / container build: zero-dependency stdio proxy to the public
# live-games endpoint of The Commons by Dead Brands, LLC (https://mcp.deadbrands.co/arena/mcp).
FROM node:20-alpine
WORKDIR /app
COPY server/proxy.mjs ./server/proxy.mjs
ENV NODE_ENV=production
ENTRYPOINT ["node", "server/proxy.mjs"]
