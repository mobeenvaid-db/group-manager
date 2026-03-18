# Group Manager — Databricks App

A lightweight Databricks App that lets account admins **delegate group membership management** to designated group managers — without giving them account admin rights.

Built with React + Tailwind (frontend) and FastAPI (backend). Uses the **workspace Account SCIM proxy** and the **Account Access Control API** with the **app’s service principal** (PAT or OAuth); user identity comes from **forwarded headers** (`X-Forwarded-Email`, `X-Forwarded-User`). No OBO for groups/SCIM; no app database.

---

## The Problem

Managing Databricks account groups has traditionally required account admin access. Letting a non-admin add or remove members from a group without giving them full admin rights is a common need.

## The Solution

This app uses Databricks’ native **Group: Manager** role. Account admins assign the Group: Manager role on a group via the app’s Admin Panel (Account Access Control API). Group managers see only groups they are allowed to manage and add/remove members — with **no OBO token** used for groups or SCIM.

- **User identity:** From request headers `X-Forwarded-Email` and `X-Forwarded-User` (set by Databricks when forwarding to the app). The app does not call IAM/SCIM with the user’s token.
- **Group and member operations:** App’s **service principal** (PAT or OAuth) → workspace Account SCIM proxy. The app enforces “group manager” in code: it lists groups and rule sets with the SP, then filters to groups where the current user (from headers) is Group: Manager or account admin.
- **Assign/revoke Group: Manager:** SP → Account Access Control API (rule sets). Only users the SP identifies as account admins can use the Admin Panel.
- **User search:** SP → workspace SCIM Users.

**In short:** OBO is only for data/compute features that have OBO scopes (e.g. SQL, files). For groups/SCIM, the app uses the **service principal** and keys off **user identity from forwarded headers**.

---

## How It Works

```
User browser
    │
    ▼
Databricks Apps gateway  ←── sets X-Forwarded-Email, X-Forwarded-User (and optionally OBO token)
    │
    ▼
FastAPI backend (main.py)
    ├── User identity from headers (X-Forwarded-Email, X-Forwarded-User) — no OBO call to IAM/SCIM
    ├── Group list/get/members → workspace Account SCIM proxy  (SP token)
    ├── Assign/revoke Group: Manager → Access Control API     (SP token)
    ├── Admin detection → Account SCIM Users                 (SP token)
    └── User search → workspace SCIM Users                    (SP token)
```

**Authentication:** The gateway sets `X-Forwarded-Email` and `X-Forwarded-User`; the backend uses these for identity. All Groups, SCIM, and Access Control API calls use the **app’s service principal** (PAT or OAuth). OBO is not used for groups or SCIM.

**Group manager enforcement:** The app lists groups and rule sets with the SP, then filters to groups where the current user (from headers) is Group: Manager or account admin. Mutations are gated the same way. Manager assignments live in Databricks (Account Access Control rule sets); no app database.

---

## Service principal required

This app does **not** use the user's OBO token for Groups or SCIM. It uses the **app's service principal** (PAT or OAuth) for all group, member, and Access Control API calls, and gets **user identity from forwarded headers** (`X-Forwarded-Email`, `X-Forwarded-User`). You do **not** need to add access-management or Groups scopes to the user token. If the SP is not configured, group and user-search endpoints return **503** with a message to set `ACCOUNT_SP_PAT` or `ACCOUNT_SP_CLIENT_ID` / `ACCOUNT_SP_CLIENT_SECRET`.


## Roles

| Role | How it's determined | What they can do |
|------|---------------------|------------------|
| **Account Admin** | SP + Account SCIM Users API | View all groups, assign/revoke Group: Manager, add/remove any member |
| **Group Manager** | Native Group: Manager role on the group (Databricks) | View and manage members of their assigned groups only (app filters by rule sets) |
| **Everyone else** | — | Sees only groups they have access to (often empty) |

---

## Prerequisites

Before deploying this app you need:

1. **Databricks CLI** installed and authenticated against your target workspace
   ```bash
   pip install databricks-cli
   databricks configure --token
   ```

2. **Node.js** (v18+) to build the React frontend locally before deploying.

3. **Service principal (required)** — The app uses the SP for all Groups, SCIM, and Access Control API calls. Provide either:
   - **PAT:** a Databricks token with access to the workspace Account SCIM proxy and Account Access Control API (set `ACCOUNT_SP_PAT` or `DATABRICKS_APP_TOKEN` in app env), or
   - **OAuth:** an account-level service principal with OAuth client ID and secret (set `ACCOUNT_SP_CLIENT_ID` and `ACCOUNT_SP_CLIENT_SECRET` via app resources). Create the SP in the [Databricks account console](https://accounts.cloud.databricks.com) under **Service Principals** and grant it access to the workspace (and Account Access Control if required).

---

## Setup

### Step 1 — Build the frontend

```bash
cd frontend
npm install
npm run build
cd ..
```

This compiles the React app into `frontend/dist/`, which FastAPI serves as static files.

### Step 2 — Configure the service principal

The app requires a service principal (PAT or OAuth) for group and SCIM operations.

**Option A — PAT:** Set app env `ACCOUNT_SP_PAT` (or `DATABRICKS_APP_TOKEN`) to a token that can call the workspace Account SCIM proxy and Account Access Control API. You can use a workspace or account-level PAT; ensure it has the right permissions.

**Option B — OAuth:** Store the SP credentials in a Databricks secret scope and register them as app resources:

```bash
# Create the scope
databricks secrets create-scope group-manager-secrets

# Add your account-level SP OAuth credentials
databricks secrets put-secret group-manager-secrets ACCOUNT_SP_CLIENT_ID \
  --string-value "<your-sp-oauth-client-id>"

databricks secrets put-secret group-manager-secrets ACCOUNT_SP_CLIENT_SECRET \
  --string-value "<your-sp-oauth-client-secret>"
```

### Step 3 — Upload the app source to the workspace

```bash
databricks sync . /Workspace/Users/<your-email>/group-manager --full
```

> The `.gitignore` excludes `frontend/node_modules/` automatically. Only the built `frontend/dist/` is uploaded.

### Step 4 — Create the app and (if using SP) register secret resources

```bash
# Create the app (one time)
databricks apps create group-manager \
  --description "Delegated group membership management"

# If you use OAuth SP (Option B), register the secret scope keys as app resources
databricks apps update group-manager --json '{
  "resources": [
    {
      "name": "ACCOUNT_SP_CLIENT_ID",
      "secret": {
        "scope": "group-manager-secrets",
        "key": "ACCOUNT_SP_CLIENT_ID",
        "permission": "READ"
      }
    },
    {
      "name": "ACCOUNT_SP_CLIENT_SECRET",
      "secret": {
        "scope": "group-manager-secrets",
        "key": "ACCOUNT_SP_CLIENT_SECRET",
        "permission": "READ"
      }
    }
  ]
}'
```

> Without a configured SP (PAT or OAuth), group list, user search, and Admin Panel endpoints return 503. Ensure `DATABRICKS_HOST` and `DATABRICKS_ACCOUNT_ID` are set (the Apps runtime usually injects these).

### Step 5 — Deploy the app

```bash
databricks apps deploy group-manager \
  --source-code-path /Workspace/Users/<your-email>/group-manager
```

### Step 6 — Open the app

Find the app URL in **Compute → Apps → group-manager** in the Databricks workspace UI, or from the CLI:

```bash
databricks apps get group-manager
```

The URL will look like: `https://group-manager-<workspace-id>.aws.databricksapps.com`

---

## Using the App

### As an Account Admin

1. Open the app URL in your browser. The workspace handles authentication automatically.
2. Click **Admin Panel** in the top navigation bar.
3. The left column lists all account groups. Use the search bar to filter.
4. Click **+ Assign Manager** on any group to open the assignment modal.
5. Type a name or email to search for a workspace user, then click **Assign**.
6. The right column shows all current assignments. Click **Revoke** to remove one.

You can also add and remove group members directly from the **Group Detail** page (click **Manage Group** on any group card from the dashboard).

### As a Group Manager

1. Open the app URL in your browser.
2. Your dashboard shows only the groups you've been assigned to manage.
3. Click **Manage Group** on any card to open the group detail view.
4. The member list shows everyone currently in the group.
5. Click **+ Add Member** to search for and add a workspace user.
6. Click **Remove** next to any member to remove them.

All changes take effect immediately in the Databricks account console.

---

## File Structure

```
group-manager/
├── app.yaml              # Databricks App config — command, env vars, secret refs
├── requirements.txt      # Python dependencies (FastAPI, httpx, etc.)
├── main.py               # FastAPI backend — all API endpoints and auth logic
├── README.md             # This file
└── frontend/
    ├── package.json
    ├── vite.config.js
    ├── tailwind.config.js
    ├── dist/             # Built React app (served by FastAPI as static files)
    └── src/
        ├── App.jsx           # Routes and layout
        ├── api.js            # All fetch calls to /api/*
        ├── context/
        │   └── AuthContext.jsx   # User identity and role state
        ├── components/
        │   ├── Header.jsx        # Navigation bar
        │   ├── Modal.jsx         # Reusable modal
        │   ├── Toast.jsx         # Success/error notifications
        │   └── Spinner.jsx       # Loading indicator
        └── pages/
            ├── Dashboard.jsx     # Group cards (scoped by role)
            ├── GroupDetail.jsx   # Member list and add/remove UI
            └── AdminPanel.jsx    # Group manager assignment UI
```

---

## Backend API Reference

| Method | Endpoint | Auth required | Description |
|--------|----------|---------------|-------------|
| GET | `/api/me` | Any user | Current user identity, admin status |
| GET | `/api/groups` | Any user | List groups (workspace proxy; user sees only groups they can access) |
| GET | `/api/groups/{id}` | Any user | Group detail with member list |
| POST | `/api/groups/{id}/members` | Manager of group or admin | Add a member `{"user_id": "..."}` |
| DELETE | `/api/groups/{id}/members/{mid}` | Manager of group or admin | Remove a member |
| GET | `/api/group-managers` | Admin only | List all Group: Manager assignments (from Access Control API) |
| POST | `/api/group-managers` | Admin only | Assign Group: Manager (Access Control API) |
| DELETE | `/api/group-managers/{assignment_id}` | Admin only | Revoke by composite id `group_id:principal_id` |
| DELETE | `/api/groups/{group_id}/managers/{principal_id}` | Admin only | Revoke Group: Manager for principal on group |
| GET | `/api/users/search?q=` | Any user | Search workspace users (workspace SCIM) |
| GET | `/api/debug` | Any user | Auth/config and redacted headers (remove in production) |
| GET | `/api/debug/auth` | Any user | Auth-pattern verification: forwarded headers, identity, SP status (no API calls) |

---

## Updating the App

After making changes to `main.py` or frontend source:

```bash
# If frontend changed, rebuild first
cd frontend && npm run build && cd ..

# Sync changes to workspace
databricks sync . /Workspace/Users/<your-email>/group-manager --full

# Redeploy
databricks apps deploy group-manager \
  --source-code-path /Workspace/Users/<your-email>/group-manager
```

---

## Verification

After deploying, confirm the following in your workspace:

1. **Access Control API paths**  
   The app calls the workspace Account Access Control proxy:
   - `GET {workspace}/api/2.0/preview/accounts/access-control/rule-sets?name=...`
   - `PUT {workspace}/api/2.0/preview/accounts/access-control/rule-sets`  
   If your account uses different paths (e.g. path-based rule set name), update `_get_rule_set` and `_update_rule_set` in `main.py`.

2. **Group Manager role name**  
   The app uses `roles/groups.manager` for the Group: Manager role. If your account uses a different role identifier (e.g. from [assignable roles for a resource](https://docs.databricks.com/api/workspace/accountaccesscontrolproxy/getassignablerolesforresource)), set the `GROUP_MANAGER_ROLE` constant in `main.py` to that value.

3. **Build and deploy**  
   After any code change, rebuild the frontend, sync to the workspace, and redeploy:
   ```bash
   cd frontend && npm run build && cd ..
   databricks sync . /Workspace/Users/<your-email>/group-manager --full
   databricks apps deploy group-manager --source-code-path /Workspace/Users/<your-email>/group-manager
   ```

---

## Troubleshooting

- **App loads but groups don't load, or I get 503 / 403**  
  The app uses a **service principal** for Groups/SCIM, not the user token. Ensure [SP is configured](#service-principal-required): set `ACCOUNT_SP_PAT` (or `DATABRICKS_APP_TOKEN`) or `ACCOUNT_SP_CLIENT_ID` / `ACCOUNT_SP_CLIENT_SECRET`. Ensure the Apps gateway forwards **X-Forwarded-Email** and **X-Forwarded-User** so the app can identify the user. If you get 403 on a specific group, the current user may not be an account admin or Group: Manager for that group.

- **User identity / 401**  
  The app reads identity from **X-Forwarded-Email** and **X-Forwarded-User**. Access the app through the Databricks workspace app URL so the gateway sets these headers.

---

## Notes

- **No app database:** Group: Manager assignments are stored in Databricks via the Account Access Control API (rule sets per group). Nothing is stored in SQLite or any app database.
- **Service principal required:** The app uses the SP for all Groups, SCIM, and Access Control API calls. When using OAuth, the SP token is cached in memory and refreshed before expiry.
- **Workspace proxy:** Group and member operations use `{workspace}/api/2.0/account/scim/v2/` with the **SP token**. The app filters the list to groups the current user (from forwarded headers) is allowed to manage (Group: Manager or account admin).
- **Empty dashboard:** Users who are not account admins and have no Group: Manager role see an empty dashboard.
