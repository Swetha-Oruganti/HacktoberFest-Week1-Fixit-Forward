# Fixit Forward

Fixit Forward turns a photo of a public issue into a clear, editable report. People can save it privately, copy or download it, and track replies manually. The app does **not** submit reports to civic authorities or claim an official status.

## What works

- React + Vite interface and Express + Node API, with MongoDB persistence (MERN).
- Sign up, sign in, and private per-account reports. Passwords are hashed and sessions use HTTP-only cookies.
- Upload a JPG, PNG, or WebP photo (8 MB limit). The server checks the file signature and only serves saved photos to their owner.
- Optional open-weight CLIP image suggestions using Transformers.js. The model runs on the Node server; images are not sent to a commercial inference API. The model downloads on its first use and needs internet access for that initial download. Set `AI_MODE=manual` to skip classification and fill the report yourself.
- Edit issue type, title, description, priority, and optional location. Copy report text or download it as `.txt`.
- Manually track “Ready to submit”, “Submitted by me”, “Acknowledged”, and “Resolved”. These statuses are not synced with an authority.

## Run locally

Requirements: Node.js 20+, npm, and Docker Desktop (for the quick local MongoDB option) or a MongoDB Atlas database. You do not need an AI API key, maps key, or paid service.

1. Start a local MongoDB container with `npm run db:up`. Or create a free MongoDB Atlas cluster: create a database user, add your current IP to **Network Access**, then choose **Connect → Drivers → Node.js** and copy the connection string. Replace `<db_password>` with the database user's password and add `/fixit-forward` before the query parameters, for example `mongodb+srv://USER:PASSWORD@cluster.example.mongodb.net/fixit-forward?retryWrites=true&w=majority`.
2. From this folder, create your local environment file:

   ```powershell
   Copy-Item .env.example .env
   ```

3. In `.env`, set a long random `JWT_SECRET`. Keep `.env` private; it is ignored by Git. If using Atlas, replace `MONGODB_URI` with your connection string. To run without downloading the image model, set `AI_MODE=manual`.
4. Install packages and start both servers:

   ```powershell
   npm install
   npm run dev
   ```

5. Open [http://localhost:5173](http://localhost:5173). The API runs on port 5000. For the first image suggestion in local AI mode, allow time for the model to download. Later use can run locally.

For a production build, run `npm run build`, then start the API with `npm start` and `NODE_ENV=production`. Set `CLIENT_ORIGIN` to the deployed frontend origin and use HTTPS so secure cookies are enabled.

## Privacy and limits

Location is requested only after the user selects the location button. Photos and reports are private to the account that uploaded them. The app does not remove EXIF metadata yet, so avoid uploading photos containing sensitive metadata. This is an MVP: before public deployment, add email verification, password recovery, photo retention cleanup, stronger anti-abuse controls, deployment backups, and privacy/legal review. Open the selected report and use **Copy report** or **Download .txt** to submit it through your local authority's actual channel.

## Project layout

```text
src/                   React app and styles
server/index.js        Express server and MongoDB connection
server/routes/api.js   Auth, upload, report, status, and export data endpoints
server/models/         MongoDB account, report, and private image records
server/services/       Open-weight image classification adapter
```
