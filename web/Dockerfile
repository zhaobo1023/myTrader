# Multi-stage Dockerfile for Next.js frontend
FROM node:20-alpine AS builder

WORKDIR /app

# NEXT_PUBLIC_* vars must be declared as ARGs so Next.js can inline them
# during the static build step. Pass with --build-arg at docker build time.
ARG NEXT_PUBLIC_POSTHOG_KEY=""
ARG NEXT_PUBLIC_POSTHOG_HOST="https://us.i.posthog.com"
ENV NEXT_PUBLIC_POSTHOG_KEY=$NEXT_PUBLIC_POSTHOG_KEY
ENV NEXT_PUBLIC_POSTHOG_HOST=$NEXT_PUBLIC_POSTHOG_HOST

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy application code
COPY . .

# Build the application
RUN npm run build

# Production stage
FROM node:20-alpine AS runner

WORKDIR /app

# Copy built application
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/public ./public

# Expose port
EXPOSE 3000

# Start the application
CMD ["npm", "start"]
