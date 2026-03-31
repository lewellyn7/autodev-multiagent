# GitHub OAuth Implementation

## Overview

This document describes the GitHub OAuth integration added to the AI Gateway FastAPI project.

## Changes Made

### 1. Database Changes (`app/database.py`)

Added `oauth_accounts` table with the following schema:

```sql
CREATE TABLE oauth_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    provider_user_id TEXT NOT NULL,
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    expires_at INTEGER,
    email TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(provider, provider_user_id)
);
```

**New Functions:**
- `init_oauth_table()` - Initialize OAuth accounts table
- `add_oauth_account()` - Add or update OAuth account
- `get_oauth_account()` - Get account by provider and user ID
- `get_all_oauth_accounts()` - Get all OAuth accounts
- `delete_oauth_account()` - Delete specific account
- `delete_oauth_account_by_provider()` - Delete all accounts for a provider
- `update_oauth_token()` - Update access/refresh tokens

### 2. API Routes (`app/main.py`)

#### OAuth Configuration
```python
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")
GITHUB_REDIRECT_URI = os.getenv("GITHUB_REDIRECT_URI", "http://localhost:8000/oauth/github/callback")
```

#### Endpoints

##### 1. `GET /oauth/github`
- **Purpose**: Redirect to GitHub OAuth authorization page
- **Scopes**: `user:email` (to get user's email address)
- **Security**: Uses secure state parameter with HMAC signature
- **Response**: 302 redirect to GitHub

##### 2. `GET /oauth/github/callback`
- **Purpose**: GitHub OAuth callback handler
- **Parameters**: 
  - `code` - Authorization code from GitHub
  - `state` - State parameter for CSRF protection
- **Process**:
  1. Validates state parameter
  2. Exchanges code for access token
  3. Fetches user info from GitHub API
  4. Stores account in database
  5. Redirects to admin dashboard
- **Response**: 302 redirect to `/`

##### 3. `GET /api/oauth/accounts`
- **Purpose**: Get list of all bound OAuth accounts
- **Auth**: Requires admin authentication (`admin_token` cookie)
- **Response**: 
```json
{
  "status": "success",
  "data": [
    {
      "id": 1,
      "provider": "github",
      "provider_user_id": "123456",
      "email": "user@example.com",
      "created_at": "2026-03-31T00:00:00"
    }
  ]
}
```

##### 4. `DELETE /api/oauth/accounts/{provider}`
- **Purpose**: Unbind OAuth account by provider
- **Auth**: Requires admin authentication
- **Parameters**: `provider` (path parameter)
- **Response**:
```json
{
  "status": "success",
  "msg": "Unbound github"
}
```

### 3. Token Refresh Logic

```python
async def refresh_github_token(provider_user_id: str, current_token: str) -> str:
    """
    Refresh GitHub access token if expired.
    Returns valid access token.
    
    Note: GitHub OAuth tokens don't expire by default unless using
    expiring tokens feature.
    """
    return current_token
```

**Note**: GitHub OAuth tokens don't expire by default. If using expiring tokens, implement refresh logic using the `refresh_token`.

## Configuration

### Environment Variables

Add these to your `.env` or environment:

```bash
# GitHub OAuth App Configuration
GITHUB_CLIENT_ID=your_client_id_here
GITHUB_CLIENT_SECRET=your_client_secret_here
GITHUB_REDIRECT_URI=http://localhost:8000/oauth/github/callback
```

### GitHub OAuth App Setup

1. Go to GitHub Settings → Developer settings → OAuth Apps
2. Click "New OAuth App"
3. Configure:
   - **Application name**: AI Gateway
   - **Homepage URL**: `http://localhost:8000`
   - **Authorization callback URL**: `http://localhost:8000/oauth/github/callback`
4. Copy Client ID and Client Secret to environment variables

## Usage

### 1. Bind GitHub Account

Visit: `http://localhost:8000/oauth/github`

This will redirect to GitHub for authorization. After approval, the account will be stored in the database.

### 2. View Bound Accounts

```bash
curl -H "Cookie: admin_token=YOUR_ADMIN_TOKEN" \
  http://localhost:8000/api/oauth/accounts
```

### 3. Unbind Account

```bash
curl -X DELETE \
  -H "Cookie: admin_token=YOUR_ADMIN_TOKEN" \
  http://localhost:8000/api/oauth/accounts/github
```

## Security Features

1. **State Parameter**: OAuth state is encoded with HMAC signature and timestamp
2. **Cookie Protection**: State stored in httponly, samesite cookie
3. **State Expiry**: State valid for 5 minutes only
4. **Admin Auth Required**: All OAuth management endpoints require admin authentication
5. **Token Storage**: Access tokens stored securely in database

## Files Modified

- `/home/lewellyn/aigateway/ai-gateway/app/database.py` - Added OAuth table and operations
- `/home/lewellyn/aigateway/ai-gateway/app/main.py` - Added OAuth routes and handlers

## Files Synced to Workspace

All changes synced to: `/home/lewellyn/.openclaw/workspace/ai-gateway-improved/`

## Next Steps

1. Configure GitHub OAuth App credentials
2. Test OAuth flow in development
3. Update production environment variables
4. Consider adding token refresh logic if using expiring tokens
5. Add OAuth account management UI to admin dashboard
