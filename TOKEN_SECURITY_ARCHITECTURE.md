# SENTINELWATCH - TOKEN SECURITY ARCHITECTURE

**Version:** 1.0
**Date:** 2026-11-12

---

## OVERVIEW

This document describes the JWT-based authentication architecture for SentinelWatch, including token lifecycle, storage, revocation, and security considerations.

---

## TOKEN ARCHITECTURE

### Access Tokens
- **Type:** JWT (RS256/HS256 configurable, default HS256)
- **Lifetime:** 15 minutes (configurable via `access_token_expire_minutes`)
- **Payload:**
  - `sub`: User ID (UUID)
  - `role`: User role (admin, analyst, viewer)
  - `exp`: Expiration timestamp (Unix epoch)
  - `iat`: Issued at timestamp
  - `type`: "access"

### Refresh Tokens
- **Type:** JWT (same algorithm as access tokens)
- **Lifetime:** 7 days (configurable via `refresh_token_expire_days`)
- **Payload:**
  - `sub`: User ID (UUID)
  - `exp`: Expiration timestamp (Unix epoch)
  - `iat`: Issued at timestamp
  - `type`: "refresh"

---

## TOKEN LIFECYCLE

```
┌─────────────┐     POST /api/v1/auth/login      ┌──────────────────┐
│   Client    │ ───────────────────────────────> │   Auth Server    │
└─────────────┘   {username, password}           └────────┬─────────┘
                                                        │
                                              ┌─────────▼─────────┐
                                              │ Validate credentials│
                                              │ Check user active   │
                                              │ Check not locked    │
                                              │ Verify Argon2id hash│
                                              └─────────┬─────────┘
                                                        │
                                              ┌─────────▼─────────┐
                                              │ Generate tokens   │
                                              │ - Access (15m)    │
                                              │ - Refresh (7d)    │
                                              │ Store refresh in  │
                                              │   user.refresh_tokens│
                                              └─────────┬─────────┘
                                                        │
                                              ┌─────────▼─────────┐
                                              │ Set HttpOnly cookie│
                                              │ Return both tokens │
                                              └───────────────────┘
                                                        │
┌─────────────┐     Set-Cookie + Body tokens       ┌────▼─────────┐
│   Client    │ <────────────────────────────────── │   Client     │
└─────────────┘   access_token + refresh_token      └──────────────┘
```

### Token Refresh Flow

```
┌─────────────┐     POST /api/v1/auth/refresh      ┌──────────────────┐
│   Client    │ ───────────────────────────────> │   Auth Server    │
└─────────────┘   {refresh_token} or Cookie      └────────┬─────────┘
                                                        │
                                              ┌─────────▼─────────┐
                                              │ Decode refresh token│
                                              │ Validate signature  │
                                              │ Check expiration    │
                                              └─────────┬─────────┘
                                                        │
                                              ┌─────────▼─────────┐
                                              │ Lookup user        │
                                              │ Check is_active    │
                                              │ Verify token in    │
                                              │ user.refresh_tokens│
                                              └─────────┬─────────┘
                                                        │
                                              ┌─────────▼─────────┐
                                              │ ROTATION:          │
                                              │ 1. Remove old token│
                                              │ 2. Generate new    │
                                              │    access + refresh │
                                              │ 3. Store new refresh│
                                              │ 4. Commit          │
                                              └─────────┬─────────┘
                                                        │
                                              ┌─────────▼─────────┐
                                              │ Set new cookie     │
                                              │ Return new tokens  │
                                              └───────────────────┘
                                                        │
┌─────────────┐     New tokens + Cookie             ┌────▼─────────┐
│   Client    │ <────────────────────────────────── │   Client     │
└─────────────┘   New tokens + Cookie               └──────────────┘
```

### Token Revocation

- **Rotation-based:** Old refresh token removed from `user.refresh_tokens` array on each refresh
- **Logout:** Removes refresh token from array, clears HttpOnly cookie
- **Compromise:** Admin can clear `user.refresh_tokens = []` to invalidate all sessions
- **Access tokens:** Remain valid until expiry (15 min) - industry standard trade-off

---

## STORAGE

### Server-Side (Database)
- **Table:** `users` column `refresh_tokens` (JSONB array)
- **Content:** Full JWT refresh token strings
- **Capacity:** Multiple concurrent sessions supported
- **Cleanup:** Automatic on rotation (old removed, new added)

### Client-Side
- **Access Token:** In memory (JavaScript variable), sent in `Authorization: Bearer` header
- **Refresh Token:**
  - **Primary:** HttpOnly cookie (`refresh_token`, Secure, SameSite=Strict, HttpOnly)
  - **Fallback:** Response body (for non-browser clients)

---

## SECURITY CONFIGURATION

### JWT Secret
- **Algorithm:** HS256 (configurable)
- **Secret Source:** Environment variable `SW_BACKEND_AUTH__JWT_SECRET`
- **Production Requirement:** Must be 32+ character cryptographically random string
- **Development:** Allows placeholder with explicit warning

### Token Expiry
| Token Type | Default | Config Variable |
|------------|---------|-----------------|
| Access | 15 minutes | `access_token_expire_minutes` |
| Refresh | 7 days | `refresh_token_expire_days` |

### Cookie Settings
| Attribute | Value |
|-----------|-------|
| HttpOnly | true |
| Secure | `config.tls.enabled` (true in production) |
| SameSite | strict |
| Max-Age | `refresh_token_expire_days * 86400` seconds |

---

## THREAT MODEL & MITIGATIONS

| Threat | Mitigation |
|--------|------------|
| Token theft (XSS) | HttpOnly cookie prevents JavaScript access |
| Token theft (MITM) | Secure cookie (HTTPS only), short access token lifetime |
| Token replay | Short access token lifetime (15 min), refresh rotation |
| Refresh token theft | Rotation invalidates old token, HttpOnly cookie |
| Refresh token reuse | Rotation invalidates old token on each refresh |
| Compromised session | Logout clears refresh token from DB and cookie |
| Mass compromise | Admin can clear all refresh_tokens for user |
| Brute force | 5 failed attempts → 15 min lockout |
| Credential stuffing | Argon2id hashing (memory-hard) |
| Token forgery | HS256 with strong secret, signature validation |

---

## LIMITATIONS & ACCEPTED RISKS

| Limitation | Risk Level | Mitigation |
|------------|------------|------------|
| Access tokens valid until expiry after logout | MEDIUM | 15-min lifetime limits exposure window |
| No access token blacklist | MEDIUM | Short lifetime (15 min) limits exposure |
| No refresh token encryption at rest | LOW | Database access required; consider encryption at rest |
| No device fingerprinting | LOW | Could be added for anomaly detection |
| No automatic session termination on password change | LOW | Could be added by clearing refresh_tokens |

---

## REVOCATION ARCHITECTURE

### Current Implementation
```
User.refresh_tokens = [token1, token2, token3]  # JSONB array

On Refresh:
  1. Validate incoming token exists in user.refresh_tokens
  2. Create new_access_token, new_refresh_token
  3. user.refresh_tokens = [t for t in user.refresh_tokens if t != old_token]
  4. user.refresh_tokens.append(new_refresh_token)
  4. await db.commit()
  5. Set new cookie, return new tokens
```

### Compromise Response
```python
# Admin action to revoke all sessions for a user
user.refresh_tokens = []
await db.commit()
# User must re-login on next request
```

---

## IMPLEMENTATION FILES

| File | Responsibility |
|------|----------------|
| `backend/src/sentinelwatch_backend/auth/jwt.py` | Token creation, decoding, verification |
| `backend/src/sentinelwatch_backend/api/v1/auth.py` | Login, refresh, logout endpoints |
| `backend/src/sentinelwatch_backend/api/deps.py` | Token validation dependencies |
| `backend/src/sentinelwatch_backend/models/user.py` | User model with refresh_tokens field |
| `backend/src/sentinelwatch_backend/config.py` | Token configuration |

---

## TESTING STRATEGY

| Test Type | Coverage |
|-----------|----------|
| Unit Tests | Token creation, decoding, verification, expiry, tampering |
| Integration Tests | Login, refresh, logout, revocation flows |
| Security Tests | Invalid tokens, expired tokens, replay attacks |
| Regression Tests | All endpoints with valid/invalid auth |

---

## FUTURE ENHANCEMENTS

1. **Access Token Blacklist** - Redis-based for immediate revocation
2. **Device Fingerprinting** - Bind refresh tokens to device/browser
3. **Anomaly Detection** - Geo-velocity, impossible travel detection
4. **Hardware Security Module (HSM)** - For production secret management
5. **OAuth2/OIDC Integration** - For SSO with enterprise identity providers
6. **Automatic Session Cleanup** - Background job to purge expired refresh tokens
