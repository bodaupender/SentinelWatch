# SentinelWatch Frontend Deployment Guide

**Version:** 1.0
**Date:** 2026-11-12

---

## Prerequisites

### System Requirements

| Component | Version |
|-----------|---------|
| Node.js | 20+ (LTS) |
| npm | 10+ |
| Nginx | 1.24+ |

---

## Build Configuration

### Environment Variables

Create `.env.production` in frontend directory:

```bash
# .env.production
VITE_API_URL=https://api.yourdomain.com/api
```

### Vite Configuration

The `vite.config.ts` is configured for production:

```typescript
// vite.config.ts
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': '/src',
      '@components': '/src/components',
      '@pages': '/src/pages',
      '@hooks': '/src/hooks',
      '@lib': '/src/lib',
      '@types': '/src/types',
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    minify: 'esbuild',
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-router-dom'],
          query: ['@tanstack/react-query'],
          table: ['@tanstack/react-table'],
          charts: ['recharts'],
          ui: ['@radix-ui/react-dialog', '@radix-ui/react-dropdown-menu'],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
```

---

## Production Build

### Build Process

```bash
cd frontend

# Install dependencies
npm ci

# Run TypeScript check
npx tsc --noEmit

# Build for production
npm run build

# Output: ./dist/
```

### Build Output Structure

```
dist/
├── index.html
├── assets/
│   ├── index-<hash>.js
│   ├── index-<hash>.css
│   ├── vendor-<hash>.js
│   ├── query-<hash>.js
│   ├── table-<hash>.js
│   ├── charts-<hash>.js
│   ├── forms-<hash>.js
│   └── icons-<hash>.js
```

### Verify Build

```bash
# Check build size
du -sh dist/

# Preview locally
npm run preview
# Opens http://localhost:4173
```

---

## Nginx Configuration

### Static File Serving

```nginx
# /etc/nginx/sites-available/sentinelwatch-frontend

server {
    listen 80;
    server_name dashboard.yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name dashboard.yourdomain.com;

    ssl_certificate /opt/sentinelwatch/certs/server.crt;
    ssl_certificate_key /opt/sentinelwatch/certs/server.key;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # HSTS
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Security headers
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options DENY;
    add_header X-XSS-Protection "1; mode=block";
    add_header Referrer-Policy "strict-origin-when-cross-origin";

    # CSP for React app
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:; connect-src 'self' https://api.yourdomain.com wss://api.yourdomain.com;" always;

    root /opt/sentinelwatch/frontend/dist;
    index index.html;

    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;

    # Cache static assets
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
        access_log off;
    }

    # SPA fallback - serve index.html for all routes
    location / {
        try_files $uri $uri/ /index.html;

        # Security headers for HTML
        add_header X-Content-Type-Options nosniff;
        add_header X-Frame-Options DENY;
        add_header X-XSS-Protection "1; mode=block";
    }

    # API proxy (optional - if not using separate API domain)
    location /api/ {
        proxy_pass https://api.yourdomain.com;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_read_timeout 30s;
        proxy_send_timeout 30s;
    }

    # Health check
    location /health {
        access_log off;
        return 200 "healthy\n";
        add_header Content-Type text/plain;
    }
}
```

### Enable Site

```bash
sudo ln -s /etc/nginx/sites-available/sentinelwatch-frontend /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## API Configuration

### Environment-Based API URL

The frontend uses `VITE_API_URL` at build time:

```bash
# Development
VITE_API_URL=http://localhost:8000/api

# Production
VITE_API_URL=https://api.yourdomain.com/api
```

### Runtime API Configuration (Optional)

For runtime configuration, create `public/config.js`:

```javascript
// public/config.js
window.SENTINELWATCH_CONFIG = {
  apiUrl: 'https://api.yourdomain.com/api',
  wsUrl: 'wss://api.yourdomain.com/ws',
};
```

Include in `index.html`:
```html
<script src="/config.js"></script>
```

Then in code:
```typescript
const apiUrl = window.SENTINELWATCH_CONFIG?.apiUrl || import.meta.env.VITE_API_URL;
```

---

## Docker Deployment (Optional)

### Multi-stage Dockerfile

```dockerfile
# Dockerfile
# Build stage
FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# Production stage
FROM nginx:alpine

# Copy custom nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built assets
COPY --from=builder /app/dist /usr/share/nginx/html

# Security headers
COPY nginx-security-headers.conf /etc/nginx/conf.d/security-headers.conf

EXPOSE 80 443

CMD ["nginx", "-g", "daemon off;"]
```

### Build and Run

```bash
# Build image
docker build -t sentinelwatch-frontend:latest .

# Run container
docker run -d \
  --name sentinelwatch-frontend \
  -p 80:80 \
  -p 443:443 \
  -v /opt/sentinelwatch/certs:/etc/nginx/certs:ro \
  sentinelwatch-frontend:latest
```

---

## Configuration Validation

### Pre-Deployment Checklist

- [ ] `VITE_API_URL` points to production API
- [ ] No development URLs in code
- [ ] No secrets in build output
- [ ] TypeScript check passes (`npx tsc --noEmit`)
- [ ] Production build completes without errors
- [ ] Nginx config tested (`nginx -t`)
- [ ] HTTPS certificates valid
- [ ] CSP allows API domain
- [ ] Static assets cached with long expiry
- [ ] SPA routing works (try_files $uri $uri/ /index.html)

### Verify Production Build

```bash
# Check no secrets in build
grep -r "CHANGE_ME\|password\|secret" dist/ || echo "No secrets found"

# Check API URL
grep -r "localhost\|127.0.0.1" dist/ || echo "No dev URLs found"

# Check CSP allows API domain
grep -r "api.yourdomain.com" dist/
```

---

## Deployment Automation

### CI/CD Pipeline (GitHub Actions Example)

```yaml
# .github/workflows/deploy-frontend.yml
name: Deploy Frontend

on:
  push:
    branches: [main]
    paths: ['frontend/**']

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json

      - name: Install dependencies
        run: cd frontend && npm ci

      - name: TypeScript check
        run: cd frontend && npx tsc --noEmit

      - name: Build
        run: cd frontend && npm run build
        env:
          VITE_API_URL: ${{ secrets.VITE_API_URL }}

      - name: Verify build
        run: |
          grep -r "localhost\|127.0.0.1" frontend/dist/ && exit 1 || true
          grep -r "CHANGE_ME\|secret" frontend/dist/ && exit 1 || true

      - name: Deploy to server
        uses: appleboy/scp-action@v0.1.4
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SERVER_SSH_KEY }}
          source: "frontend/dist/"
          target: "/opt/sentinelwatch/frontend/dist"
          strip_components: 1

      - name: Reload nginx
        uses: appleboy/ssh-action@v1.0.0
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SERVER_SSH_KEY }}
          script: |
            sudo nginx -t && sudo systemctl reload nginx
```

---

## Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Blank page on refresh | SPA routing | Add `try_files $uri $uri/ /index.html` |
| API calls fail | CORS | Check `VITE_API_URL` and CORS config |
| Blank page on build | Build error | Check `npm run build` output |
| 404 on refresh | SPA routing | Nginx `try_files` config |
| API calls blocked | CSP | Update CSP `connect-src` |
| Static assets 404 | Path mismatch | Check `root` and `try_files` |

### Debug Commands

```bash
# Check nginx config
nginx -t

# View nginx logs
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log

# Check static files
ls -la /opt/sentinelwatch/frontend/dist/

# Test API proxy
curl -v https://dashboard.yourdomain.com/api/health

# Check CSP headers
curl -I https://dashboard.yourdomain.com | grep -i content-security-policy
```

---

## Performance Optimization

### Build Optimizations (Already Configured)

```typescript
// vite.config.ts - Already configured
build: {
  minify: 'esbuild',
  cssCodeSplit: true,
  rollupOptions: {
    output: {
      manualChunks: {
        vendor: ['react', 'react-dom', 'react-router-dom'],
        query: ['@tanstack/react-query'],
        table: ['@tanstack/react-table'],
        charts: ['recharts'],
      },
    },
  },
}
```

### Nginx Optimizations

```nginx
# Enable compression
gzip on;
gzip_vary on;
gzip_min_length 1024;
gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;

# Cache static assets
location /assets/ {
    expires 1y;
    add_header Cache-Control "public, immutable";
    access_log off;
}

# HTTP/2
listen 443 ssl http2;
```

---

## Rollback Procedure

```bash
# 1. Keep previous build
mv /opt/sentinelwatch/frontend/dist /opt/sentinelwatch/frontend/dist.backup.$(date +%Y%m%d)

# 2. Deploy new build
# (copy new dist to /opt/sentinelwatch/frontend/dist)

# 3. Test
curl -I https://dashboard.yourdomain.com

# 4. If issues, rollback
mv /opt/sentinelwatch/frontend/dist /opt/sentinelwatch/frontend/dist.failed.$(date +%Y%m%d)
mv /opt/sentinelwatch/frontend/dist.backup.* /opt/sentinelwatch/frontend/dist
sudo systemctl reload nginx
```
