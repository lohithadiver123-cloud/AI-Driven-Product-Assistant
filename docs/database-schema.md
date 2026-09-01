# Database Schema Documentation — MongoDB Atlas

## 1. Database Architecture & Collections

**Database Name**: `ai_product_assistant`  
**Driver**: `Motor` (Async Python MongoDB Driver) & `PyMongo`

### Collection Status Overview
| Collection Name | Status | Purpose |
|---|---|---|
| `users` | **ACTIVE / IMPLEMENTED** | User identities, Argon2id password hashes, roles, and workspace links |
| `workspaces` | **ACTIVE / IMPLEMENTED** | Multi-tenant product workspaces, owner reference, and member roles |
| `refresh_tokens` | **ACTIVE / IMPLEMENTED** | SHA-256 hashed rotatable refresh tokens with session revocation support |
| `password_reset_tokens` | **ACTIVE / IMPLEMENTED** | Cryptographic single-use, 30-min password reset tokens (SHA-256 hashed) |
| `email_verification_tokens` | **ACTIVE / IMPLEMENTED** | Single-use 24-hr account verification tokens (SHA-256 hashed) |
| `feedback` | **ACTIVE / IMPLEMENTED** | Stores customer reviews, surveys, user feedback scoped by `workspace_id` |
| `support_tickets` | **ACTIVE / IMPLEMENTED** | Stores customer tickets and issue reports scoped by `workspace_id` |
| `feature_requests` | **SCHEMA DEFINED** (Milestone 2) | Future repository for clustered and prioritized product feature items |
| `themes` | **PLANNED** (Milestone 2) | Future repository for semantic clusters of feedback pain points |
| `analytics` | **PLANNED** (Milestone 2) | Historical trend metrics and sentiment trajectories |

---

## 2. Active Collections Detail

### 2.1. `users` Collection
Stores user profiles and credential hashes.

```json
{
  "_id": "ObjectId",
  "name": "String (e.g. Alex Founder)",
  "email": "String (unique index, lowercase, e.g. alex@example.com)",
  "password_hash": "String (Argon2id cryptographic hash)",
  "role": "String (OWNER, ADMIN, MEMBER, VIEWER)",
  "email_verified": "Boolean (default false)",
  "workspace_ids": ["String (Array of linked workspace IDs)"],
  "current_workspace_id": "String (Active workspace ID)",
  "is_active": "Boolean (default true)",
  "created_at": "ISODate",
  "updated_at": "ISODate",
  "last_login_at": "ISODate (optional)"
}
```

---

### 2.2. `workspaces` Collection
Multi-tenant organizational workspaces partitioning all customer data.

```json
{
  "_id": "ObjectId",
  "name": "String (e.g. Acme SaaS Product Hub)",
  "owner_id": "String (User ID of the workspace creator)",
  "members": [
    {
      "user_id": "String",
      "name": "String",
      "email": "String",
      "role": "String (OWNER, ADMIN, MEMBER, VIEWER)",
      "joined_at": "ISODate"
    }
  ],
  "created_at": "ISODate",
  "updated_at": "ISODate"
}
```

---

### 2.3. `refresh_tokens` Collection
Stores hashed refresh tokens supporting multi-device sessions and instant revocation.

```json
{
  "_id": "ObjectId",
  "user_id": "String",
  "token_hash": "String (unique SHA-256 hash of random token)",
  "device_info": "String (e.g. Web Dashboard)",
  "expires_at": "ISODate (14-day expiry)",
  "revoked_at": "ISODate (optional, null when active)",
  "created_at": "ISODate"
}
```

---

### 2.4. `password_reset_tokens` Collection
Single-use password recovery tokens.

```json
{
  "_id": "ObjectId",
  "user_id": "String",
  "token_hash": "String (unique SHA-256 hash)",
  "expires_at": "ISODate (30-min expiry)",
  "used_at": "ISODate (optional, null until consumed)",
  "created_at": "ISODate"
}
```

---

### 2.5. `email_verification_tokens` Collection
Single-use email verification tokens.

```json
{
  "_id": "ObjectId",
  "user_id": "String",
  "token_hash": "String (unique SHA-256 hash)",
  "expires_at": "ISODate (24-hr expiry)",
  "used_at": "ISODate (optional, null until consumed)",
  "created_at": "ISODate"
}
```

---

### 2.6. `feedback` Collection
Customer feedback signals partitioned by `workspace_id`.

```json
{
  "_id": "ObjectId",
  "workspace_id": "String (required partition key)",
  "customer_id": "String (optional, e.g. CUST-1001)",
  "source": "String (required, e.g. Zendesk, AppStore, Trustpilot, CSV Import)",
  "type": "String (required, default 'review')",
  "text": "String (required, verbatim customer text)",
  "cleaned_text": "String (sanitized text)",
  "category": "String (controlled 10 domains)",
  "category_confidence": "Double (0.00 to 1.00)",
  "sentiment": "String (Positive, Neutral, Negative)",
  "priority": "String (Urgent, High, Medium, Low)",
  "status": "String (default 'New')",
  "created_at": "ISODate",
  "updated_at": "ISODate",
  "metadata": "Object"
}
```

---

### 2.7. `support_tickets` Collection
Customer support incidents partitioned by `workspace_id`.

```json
{
  "_id": "ObjectId",
  "workspace_id": "String (required partition key)",
  "ticket_id": "String (e.g. TIK-4001)",
  "customer_id": "String (optional)",
  "source": "String (Zendesk, Intercom, Email, Jira, Support Portal)",
  "text": "String (verbatim customer problem description)",
  "cleaned_text": "String (sanitized issue text)",
  "category": "String (controlled 10 domains)",
  "category_confidence": "Double (0.00 to 1.00)",
  "sentiment": "String (Positive, Neutral, Negative)",
  "priority": "String (Urgent, High, Medium, Low)",
  "status": "String (Open, In-Progress, Resolved, Closed)",
  "created_at": "ISODate",
  "updated_at": "ISODate",
  "metadata": "Object"
}
```

---

## 3. Database Indexes
The following indexes are automatically created at application startup:
1. `users.email` (Unique)
2. `workspaces.owner_id` & `workspaces.members.user_id`
3. `refresh_tokens.token_hash` (Unique) & `refresh_tokens.user_id`
4. `password_reset_tokens.token_hash` (Unique) & `password_reset_tokens.user_id`
5. `email_verification_tokens.token_hash` (Unique) & `email_verification_tokens.user_id`
6. `feedback.workspace_id` & `feedback.category`
7. `support_tickets.workspace_id`
