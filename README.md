# Group Manager — Databricks App

A lightweight Databricks App that lets account admins **delegate group membership management** to designated group managers — without giving them account admin rights.

Built with React + Tailwind (frontend) and FastAPI (backend). Uses the **workspace Account SCIM proxy** and the **Account Access Control API** so group managers use their own token; no app database and (optionally) no Service Principal required for group-manager flows.

---

## The Problem

Managing Databricks account groups has traditionally required account admin access. Letting a non-admin add or remove members from a group without giving them full admin rights is a common need.

## The Solution

This app uses Databricks’ native **Group: Manager** role. Account admins (or workspace admins) assign the Group: Manager role on a group via the app’s Admin Panel, which calls the **Account Access Control API**. Group managers then use the **workspace Account SCIM proxy** with their own token to list groups they manage and add/remove members — no Account Admin Service Principal or app database required for those operations.

- **Group and member operations:** User’s OBO token → `{workspace}/api/2.0/account/scim/v2/` (workspace proxy). Databricks enforces which groups the user can see and modify.
- **Assign/revoke Group: Manager:** User’s token → Account Access Control API (rule sets on each group). Manager assignments live in Databricks, not in the app.
- **Admin detection (optional):** If an account-admin Service Principal is configured, the app uses it to detect account admins so the Admin Panel is shown and “list all groups” works for them.

---

## How It Works

```
User browser
    │
    ▼
Databricks Apps gateway  ←── injects X-Forwarded-Access-Token (OBO token)
    │
    ▼
FastAPI backend (main.py)
    ├── Identifies the user via /api/2.0/preview/scim/v2/Me     (OBO token)
    ├── Group list/get/members → workspace Account SCIM proxy  (OBO token)
    ├── Assign/revoke Group: Manager → Access Control API      (OBO token)
    ├── Admin detection (optional) → Account SCIM Users        (SP token, if configured)
    └── User search → workspace SCIM Users                     (OBO token)
```

**Authentication (OBO):** The Databricks Apps gateway injects the user’s token as `X-Forwarded-Access-Token`. The backend uses this for all group and member operations and for the Access Control API.

**Group manager assignments:** Stored in Databricks as the **Group: Manager** role on each group (Account Access Control rule sets). No SQLite or app database.

**Optional Service Principal:** Configure an account-admin SP only if you want the app to detect account admins and show the Admin Panel. Group managers do not need the SP.

---

## Roles

| Role | How it's determined | What they can do |
|------|---------------------|------------------|
| **Account Admin** | SP + Account SCIM Users API (if SP configured) | View all groups, assign/revoke Group: Manager, add/remove any member |
| **Group Manager** | Native Group: Manager role on the group (Databricks) | View and manage members of their assigned groups only (via workspace proxy) |
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

3. **(Optional) Account-admin Service Principal** — Only required if you want the app to detect account admins and show the Admin Panel. Group managers can use the app without any SP. If you want the Admin Panel, create an account-admin SP in the [Databricks account console](https://accounts.cloud.databricks.com) under **Service Principals** and add OAuth credentials (client ID + secret).

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

### Step 2 — (Optional) Create the secret scope and add SP credentials

Only needed if you want the Admin Panel and account-admin detection. The SP credentials are stored as Databricks secrets.

```bash
# Create the scope
databricks secrets create-scope group-manager-secrets

# Add your account-admin SP credentials
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

# If you configured SP in Step 2, register the secret scope keys as app resources
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

> If you skip the SP and secret registration, the app still works for group managers; the Admin Panel will not be shown because the app cannot detect account admins. You can add the SP and resources later and redeploy.

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
| GET | `/api/debug` | Any user | Auth diagnostics (remove in production) |

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

## Notes

- **No app database:** Group: Manager assignments are stored in Databricks via the Account Access Control API (rule sets per group). Nothing is stored in SQLite or any app database.
- **SP optional:** If you do not configure the Service Principal, the app works for group managers (they use the workspace Account SCIM proxy with their own token). The Admin Panel and account-admin detection require the SP. When configured, the SP token is cached in memory for 55 minutes.
- **Workspace proxy:** Group and member operations use `{workspace}/api/2.0/account/scim/v2/` with the user’s token. Databricks returns only groups the user is allowed to see or manage.
- **Non-admins with no groups:** Users who are not account admins and have no Group: Manager role see an empty dashboard.
