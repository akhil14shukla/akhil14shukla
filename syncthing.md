# Google Antigravity Multi-Device Synchronization Guide

This guide provides a generic, step-by-step workflow to synchronize your Google Antigravity chat history, agent states, project configurations, and workspaces across multiple macOS devices using **Syncthing** over a secure network (such as **Tailscale**).

---

## 1. Antigravity Storage Architecture

To achieve seamless synchronization, you must understand how Antigravity manages data:
* **Conversations & Brain State:** Individual chats are saved as `.pb` (Protocol Buffer) files in `~/.gemini/antigravity/conversations/`. The agent's task checklists, plans, and workspace logs are in `~/.gemini/antigravity/brain/`.
* **The Summaries Index (`agyhub_summaries_proto.pb`):** Located in `~/.gemini/antigravity/`, this file acts as the database index for the IDE Inbox. It hardcodes absolute paths to workspaces and maps conversations to specific **Project IDs**.
* **Project Configurations:** Located in `~/.gemini/config/projects/`, these JSON files assign a unique Project UUID to each codebase path. *If these UUIDs differ between machines, the synced conversations will not appear in the IDE Inbox.*

---

## 2. Prerequisites

1. **Tailscale:** Install and run [Tailscale](https://tailscale.com/) on all devices to establish a secure, peer-to-peer connection.
2. **Syncthing:** Install [Syncthing](https://syncthing.net/) via Homebrew on both Macs:
   ```bash
   brew install syncthing
   brew services start syncthing
   ```
   Access the Syncthing Web UI at [http://localhost:8384/](http://localhost:8384/).

---

## 3. Step-by-Step Configuration

### Step 1: Align Username Path Discrepancies (Symmetric Symlinks)
If your macOS usernames differ between machines (e.g., `macA` uses `/Users/userA` and `macB` uses `/Users/userB`), the absolute paths in the summaries index won't resolve. 

To fix this, create mutual symlinks on both machines:
* **On Device A (`userA`):**
  ```bash
  sudo ln -s /Users/userA /Users/userB
  ```
* **On Device B (`userB`):**
  ```bash
  sudo ln -s /Users/userB /Users/userA
  ```
*This ensures `/Users/userA/` paths resolve correctly on Device B, and vice-versa.*

---

### Step 2: Configure Shared Folders in Syncthing
Add and share the following three directories in Syncthing between the devices:

#### Folder 1: Antigravity Core
* **Folder ID:** `antigravity-core`
* **Local Path (Device A):** `/Users/userA/.gemini/antigravity`
* **Remote Path (Device B):** `/Users/userB/.gemini/antigravity`
* **Purpose:** Syncs all conversations, brain states, and the main `agyhub_summaries_proto.pb` index.

#### Folder 2: Projects Configuration (Crucial for Inbox matching)
* **Folder ID:** `antigravity-projects-config`
* **Local Path (Device A):** `/Users/userA/.gemini/config/projects`
* **Remote Path (Device B):** `/Users/userB/.gemini/config/projects`
* **Purpose:** Ensures both devices map the same workspace paths to the exact same **Project UUIDs**.
* **Note:** *Before setting this up, make sure to delete or back up any existing project JSON files on the destination machine so they are replaced by the source machine's config files.*

#### Folder 3: Code Workspaces
* **Folder ID:** `antigravity-workspaces`
* **Local Path (Device A):** Your codebase path (e.g., `/Users/userA/Projects`)
* **Remote Path (Device B):** Your codebase path (e.g., `/Users/userB/Projects`)
* **Purpose:** Syncs your code files, Git branches, and work states.

---

### Step 3: Setup Ignore Patterns (`.stignore`)
To optimize bandwidth and avoid syncing architecture-specific binaries or massive build folders, configure ignore rules in the Syncthing Web UI (under **Folder Settings > Ignore Patterns**):

* **For `antigravity-core`:**
  ```
  bin/
  ```
  *(Prevents syncing architecture-specific language server and Node.js binaries).*

* **For `antigravity-workspaces`:**
  ```
  dist
  build
  node_modules
  .DS_Store
  ```

---

### Step 4: Reload and Verify

1. Let Syncthing complete the initial synchronization (the status will change to `idle`).
2. If the files are synced while the IDE is open, restart the **Antigravity desktop application** on the receiving machine so the backend language server reloads the new summaries index and project mappings.
3. Your chat history, active tasks, and codebases will now be fully synced and ready to use!

---

## 4. Troubleshooting & Common Issues

### Issue A: Upload and Download Rates are 0 B/s (Idle)
* **Explanation:** When Syncthing shows `0 B/s` and the folder state is `Idle` (or `Up to Date`), this is the **correct, expected behavior**. It indicates that both machines are fully synchronized and there is no active data to transfer.
* **Verification:** Try creating a small temporary text file in one of the synced directories. Within 10-15 seconds, you should see the folder scan, transfer rates momentarily spike, and then return to `0 B/s` as it goes back to `Idle`.

### Issue B: "Folder Marker Missing" Error
* **Symptom:** In the Syncthing Web UI, a folder turns red and displays: `folder marker missing (this indicates potential data loss...)`.
* **Explanation:** Syncthing creates an empty folder named `.stfolder` inside every sync directory as a safety check to ensure the directory is still mounted. If it gets deleted, Syncthing stops syncing the folder entirely to prevent accidental data loss.
* **Fix:** Manually recreate the missing directory on the machine reporting the error.
  ```bash
  mkdir -p /path/to/synced-folder/.stfolder
  ```
  Once created, trigger a rescan or restart Syncthing to clear the error.

### Issue C: macOS Service Startup or Bootstrap Errors
* **Symptom:** Running `brew services start syncthing` or `brew services restart syncthing` fails with: `Bootstrap failed: 5: Input/output error` or status remains as `other`.
* **Fix:** The service is already registered under launchd but might be stuck. You can force-restart it using macOS's built-in `launchctl` command (replace `501` with your user ID, which you can find by running `id -u`):
  ```bash
  launchctl kickstart -kp gui/501/homebrew.mxcl.syncthing
  ```

---

## 5. Preventative Practices

### A. Lock the `.stfolder` Safety Directory (Recommended)
To prevent build tools, cleanup scripts, or commands like `git clean -fdx` from deleting the hidden `.stfolder` directory, lock it with the macOS **immutable flag** (`uchg`):
```bash
chflags uchg /path/to/synced-folder/.stfolder
```
*Note: If you ever need to delete or move this folder in the future, you can unlock it first by running:*
```bash
chflags nouchg /path/to/synced-folder/.stfolder
```

### B. Add `.stfolder` to Git Ignore Rules
For any synced folder that is a Git repository, add `.stfolder` to your local `.gitignore` or global `~/.gitignore_global`:
```
.stfolder/
```

### C. Create a Shell Alias for Service Recovery
To quickly revive a stuck or frozen Syncthing launchd daemon on macOS, add this helper alias to your shell profile (`~/.zshrc` or `~/.bash_profile`):
```bash
alias recovery-shell="launchctl kickstart -kp gui/\$(id -u)/homebrew.mxcl.syncthing"
```
Now, simply typing `recovery-shell` will instantly force-revive the background service.

