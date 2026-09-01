# REST API Reference Manual

**Base URL**: `http://localhost:8000`  
**API Prefix**: `/api/v1`  
**Interactive Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)  
**ReDoc Specification**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 1. Authentication Endpoints (`/api/v1/auth`)

### `POST /api/v1/auth/register`
Registers a new user account and provisions their default workspace.
* **Payload**:
```json
{
  "name": "Sarah Connor",
  "email": "sarah@company.com",
  "password": "SecurePassword123",
  "confirm_password": "SecurePassword123",
  "workspace_name": "Skynet Product Hub"
}
```
* **Response `201 Created`**:
```json
{
  "access_token": "eyJhbGciOi...",
  "refresh_token": "a1b2c3d4...",
  "token_type": "bearer",
  "expires_in": 1800,
  "user": {
    "id": "60d5ec49f1b2c8a1d4f00001",
    "name": "Sarah Connor",
    "email": "sarah@company.com",
    "role": "OWNER",
    "email_verified": false,
    "current_workspace_id": "60d5ec49f1b2c8a1d4f00002",
    "workspace_name": "Skynet Product Hub"
  }
}
```

### `POST /api/v1/auth/login`
Authenticates credentials and returns new JWT access & refresh tokens.
* **Payload**:
```json
{
  "email": "sarah@company.com",
  "password": "SecurePassword123"
}
```

### `POST /api/v1/auth/refresh`
Rotates refresh token and returns new session tokens.
* **Payload**:
```json
{
  "refresh_token": "a1b2c3d4..."
}
```

### `POST /api/v1/auth/logout`
Revokes active refresh token session.
* **Payload**:
```json
{
  "refresh_token": "a1b2c3d4..."
}
```

### `GET /api/v1/auth/me`
* **Headers**: `Authorization: Bearer <access_token>`
* **Response `200 OK`**: Current user profile and active workspace context.

### `POST /api/v1/auth/verify-email`
Verifies user email with token.
* **Payload**: `{"token": "string"}`

### `POST /api/v1/auth/forgot-password`
Dispatches password reset link (anti-enumeration protected).
* **Payload**: `{"email": "user@company.com"}`

### `POST /api/v1/auth/reset-password`
Consumes reset token and updates password.
* **Payload**:
```json
{
  "token": "string",
  "new_password": "NewSecurePassword123",
  "confirm_password": "NewSecurePassword123"
}
```

### `POST /api/v1/auth/change-password`
* **Headers**: `Authorization: Bearer <access_token>`
* **Payload**:
```json
{
  "current_password": "OldPassword123",
  "new_password": "NewSecurePassword123",
  "confirm_password": "NewSecurePassword123"
}
```

---

## 2. Workspaces Endpoints (`/api/v1/workspaces`)

* `GET /api/v1/workspaces`: List user's workspaces.
* `POST /api/v1/workspaces`: Create a new workspace.
* `GET /api/v1/workspaces/current`: Get active workspace details & members.
* `POST /api/v1/workspaces/switch/{workspace_id}`: Switch active workspace context.
* `POST /api/v1/workspaces/members`: Add member (`OWNER`/`ADMIN` only).
* `PATCH /api/v1/workspaces/members/{user_id}`: Update member role (`OWNER`/`ADMIN` only).
* `DELETE /api/v1/workspaces/members/{user_id}`: Remove member (`OWNER` only).

---

## 3. Customer Feedback Endpoints (`/api/v1/feedback`)
*(All endpoints are scoped by the active workspace)*

* `GET /api/v1/feedback/stats`: Real-time aggregated metrics for active workspace.
* `GET /api/v1/feedback/categories`: 10 controlled categories with item counts.
* `POST /api/v1/feedback/upload`: Ingest feedback CSV dataset (`OWNER`/`ADMIN`/`MEMBER`).
* `POST /api/v1/feedback/upload-json`: Ingest feedback JSON records (`OWNER`/`ADMIN`/`MEMBER`).
* `POST /api/v1/feedback`: Create single feedback item (`OWNER`/`ADMIN`/`MEMBER`).
* `GET /api/v1/feedback`: Paginated query with search, category, sentiment, priority filters.
* `GET /api/v1/feedback/{id}`: Single feedback inspection.
* `PATCH /api/v1/feedback/{id}`: Update feedback item (`OWNER`/`ADMIN`/`MEMBER`).
* `DELETE /api/v1/feedback/{id}`: Delete feedback item (`OWNER`/`ADMIN`).

---

## 4. Customer Support Tickets Endpoints (`/api/v1/support-tickets`)
*(All endpoints are scoped by the active workspace)*

* `GET /api/v1/support-tickets/stats`: Support tickets distribution metrics.
* `POST /api/v1/support-tickets/upload`: Ingest support tickets CSV (`OWNER`/`ADMIN`/`MEMBER`).
* `POST /api/v1/support-tickets/upload-json`: Ingest support tickets JSON array (`OWNER`/`ADMIN`/`MEMBER`).
* `POST /api/v1/support-tickets`: Create single ticket record (`OWNER`/`ADMIN`/`MEMBER`).
* `GET /api/v1/support-tickets`: Paginated query with filters.
* `GET /api/v1/support-tickets/{id}`: Single ticket inspection.
* `PATCH /api/v1/support-tickets/{id}`: Update support ticket (`OWNER`/`ADMIN`/`MEMBER`).
* `DELETE /api/v1/support-tickets/{id}`: Delete support ticket (`OWNER`/`ADMIN`).

---

## 5. System Health & Diagnostics (Public)

* `GET /`: App root metadata.
* `GET /health`: Server health ping.
* `GET /health/database`: MongoDB latency & connectivity check.
