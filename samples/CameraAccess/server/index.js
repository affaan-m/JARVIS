const http = require("http");
const fs = require("fs");
const path = require("path");
const { WebSocketServer, WebSocket } = require("ws");
const crypto = require("crypto");

const PORT = process.env.PORT || 8080;
const rooms = new Map(); // roomCode -> { creator: ws, viewers: Map<viewerId, ws>, destroyTimer: timeout|null }

// Grace period (ms) before destroying a room when creator disconnects.
// Allows the iOS user to switch apps (e.g. copy room code, send via WhatsApp) and come back.
const ROOM_GRACE_PERIOD_MS = 60_000;

// Max viewers per room
const MAX_VIEWERS = 5;

// TURN: Metered TURN (free tier 500MB/month)
const METERED_APP = process.env.METERED_APP || "ciri.metered.live";
const METERED_API_KEY = process.env.METERED_API_KEY || "4ea9c11f97051f7c257c72ef8ef6bf34ace6";

// Cache TURN credentials (refresh every 10 minutes since Metered issues time-limited creds)
let cachedTurnCreds = null;
let turnCacheExpiry = 0;
const TURN_CACHE_TTL_MS = 10 * 60 * 1000;

async function fetchTurnCredentials() {
  const now = Date.now();
  if (cachedTurnCreds && now < turnCacheExpiry) return cachedTurnCreds;

  try {
    const url = `https://${METERED_APP}/api/v1/turn/credentials?apiKey=${METERED_API_KEY}`;
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`Metered API ${resp.status}`);
    const servers = await resp.json();
    cachedTurnCreds = { iceServers: servers };
    turnCacheExpiry = now + TURN_CACHE_TTL_MS;
    console.log(`[TURN] Fetched ${servers.length} ICE servers from Metered`);
    return cachedTurnCreds;
  } catch (e) {
    console.error("[TURN] Failed to fetch Metered credentials:", e.message);
    // Return STUN-only fallback
    return { iceServers: [{ urls: "stun:stun.l.google.com:19302" }] };
  }
}

function generateViewerId() {
  return crypto.randomBytes(4).toString("hex");
}

// HTTP server for serving the web viewer
const httpServer = http.createServer((req, res) => {
  // TURN credentials API endpoint
  if (req.url === "/api/turn") {
    fetchTurnCredentials().then((creds) => {
      res.writeHead(200, {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
      });
      res.end(JSON.stringify(creds));
    }).catch((e) => {
      res.writeHead(500);
      res.end(JSON.stringify({ error: e.message }));
    });
    return;
  }

  let filePath = path.join(
    __dirname,
    "public",
    req.url === "/" ? "index.html" : req.url
  );

  const ext = path.extname(filePath);
  const contentTypes = {
    ".html": "text/html",
    ".js": "application/javascript",
    ".css": "text/css",
  };

  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(404);
      res.end("Not found");
      return;
    }
    res.writeHead(200, {
      "Content-Type": contentTypes[ext] || "text/plain",
    });
    res.end(data);
  });
});

// WebSocket signaling server
const wss = new WebSocketServer({ server: httpServer });

// Ping/pong heartbeat to keep connections alive through Fly.io proxy
// and detect dead connections within ~25-50 seconds
const PING_INTERVAL_MS = 25_000;
const pingInterval = setInterval(() => {
  wss.clients.forEach((ws) => {
    if (ws.isAlive === false) {
      console.log(`[WS] Terminating dead connection (no pong response)`);
      return ws.terminate();
    }
    ws.isAlive = false;
    ws.ping();
  });
}, PING_INTERVAL_MS);
wss.on("close", () => clearInterval(pingInterval));

// Fixed room code so the viewer can always connect with the same code
const FIXED_ROOM_CODE = "VCLAW1";

function generateRoomCode() {
  return FIXED_ROOM_CODE;
}

wss.on("connection", (ws, req) => {
  let currentRoom = null;
  let role = null; // 'creator' or 'viewer'
  const clientIP = req.headers["x-forwarded-for"] || req.socket.remoteAddress;
  console.log(`[WS] New connection from ${clientIP}`);

  // Track connection liveness for ping/pong
  ws.isAlive = true;
  ws.on("pong", () => { ws.isAlive = true; });

  ws.on("message", (data) => {
    let msg;
    try {
      msg = JSON.parse(data);
    } catch {
      return;
    }

    switch (msg.type) {
      case "create": {
        const code = generateRoomCode();
        // If the fixed room already exists, clean it up first
        if (rooms.has(code)) {
          const oldRoom = rooms.get(code);
          if (oldRoom.destroyTimer) clearTimeout(oldRoom.destroyTimer);
          // Notify and close all existing viewers
          for (const [vid, viewerWs] of oldRoom.viewers) {
            if (viewerWs.readyState === WebSocket.OPEN) {
              viewerWs.send(JSON.stringify({ type: "peer_left" }));
              viewerWs.close(1000, "room_replaced");
            }
          }
          oldRoom.viewers.clear();
          if (oldRoom.creator && oldRoom.creator !== ws && oldRoom.creator.readyState === WebSocket.OPEN) {
            oldRoom.creator.close();
          }
          rooms.delete(code);
          console.log(`[Room] Replaced existing room: ${code}`);
        }
        rooms.set(code, { creator: ws, viewers: new Map(), destroyTimer: null });
        currentRoom = code;
        role = "creator";
        ws.send(JSON.stringify({ type: "room_created", room: code }));
        console.log(`[Room] Created: ${code}`);
        break;
      }

      case "rejoin": {
        // Creator reconnects to an existing room (after app backgrounding)
        const room = rooms.get(msg.room);
        if (!room) {
          ws.send(
            JSON.stringify({ type: "error", message: "Room not found" })
          );
          return;
        }
        // Cancel the destroy timer since creator is back
        if (room.destroyTimer) {
          clearTimeout(room.destroyTimer);
          room.destroyTimer = null;
          console.log(`[Room] Creator rejoined, cancelled destroy timer: ${msg.room}`);
        }
        room.creator = ws;
        currentRoom = msg.room;
        role = "creator";
        ws.send(JSON.stringify({ type: "room_rejoined", room: msg.room }));
        // Notify creator about each existing viewer so it re-negotiates with each
        for (const [viewerId, viewerWs] of room.viewers) {
          if (viewerWs.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "peer_joined", viewerId }));
            console.log(`[Room] Notifying rejoined creator about viewer ${viewerId}: ${msg.room}`);
          }
        }
        console.log(`[Room] Creator rejoined: ${msg.room}`);
        break;
      }

      case "join": {
        const room = rooms.get(msg.room);
        if (!room) {
          ws.send(
            JSON.stringify({ type: "error", message: "Room not found" })
          );
          return;
        }
        if (room.viewers.size >= MAX_VIEWERS) {
          ws.send(JSON.stringify({ type: "error", message: "Room is full (max " + MAX_VIEWERS + " viewers)" }));
          return;
        }
        const viewerId = generateViewerId();
        ws.viewerId = viewerId;
        room.viewers.set(viewerId, ws);
        currentRoom = msg.room;
        role = "viewer";
        ws.send(JSON.stringify({ type: "room_joined", viewerId }));
        // Notify creator that a viewer joined (with viewerId so it can create a dedicated peer connection)
        if (room.creator && room.creator.readyState === WebSocket.OPEN) {
          room.creator.send(JSON.stringify({ type: "peer_joined", viewerId }));
        }
        console.log(`[Room] Viewer ${viewerId} joined: ${msg.room} (${room.viewers.size} viewer(s))`);
        break;
      }

      // Relay SDP and ICE candidates between creator and specific viewer
      case "offer":
      case "answer":
      case "candidate": {
        const room = rooms.get(currentRoom);
        if (!room) {
          console.log(`[Relay] ${msg.type} from ${role} but room ${currentRoom} not found`);
          return;
        }

        if (role === "creator") {
          // Creator -> specific viewer (msg must include viewerId)
          const targetViewerId = msg.viewerId;
          if (!targetViewerId) {
            console.log(`[Relay] ${msg.type} from creator missing viewerId`);
            return;
          }
          const targetViewer = room.viewers.get(targetViewerId);
          if (targetViewer && targetViewer.readyState === WebSocket.OPEN) {
            targetViewer.send(JSON.stringify(msg));
            console.log(`[Relay] ${msg.type} from creator -> viewer ${targetViewerId} (room ${currentRoom})`);
          } else {
            console.log(`[Relay] ${msg.type} from creator but viewer ${targetViewerId} not ready (room ${currentRoom})`);
          }
        } else {
          // Viewer -> creator (attach viewerId from the ws)
          const relayMsg = { ...msg, viewerId: ws.viewerId };
          if (room.creator && room.creator.readyState === WebSocket.OPEN) {
            room.creator.send(JSON.stringify(relayMsg));
            console.log(`[Relay] ${msg.type} from viewer ${ws.viewerId} -> creator (room ${currentRoom})`);
          } else {
            console.log(`[Relay] ${msg.type} from viewer ${ws.viewerId} but creator not ready (room ${currentRoom})`);
          }
        }
        break;
      }
    }
  });

  ws.on("error", (err) => {
    console.log(`[WS] Error for ${role} in room ${currentRoom}: ${err.message}`);
  });

  ws.on("close", (code, reason) => {
    console.log(`[WS] Closed: ${role} in room ${currentRoom} (code=${code}, reason=${reason || "none"})`);

    if (currentRoom && rooms.has(currentRoom)) {
      const room = rooms.get(currentRoom);

      if (role === "creator") {
        // Notify ALL viewers that the creator left
        for (const [viewerId, viewerWs] of room.viewers) {
          if (viewerWs.readyState === WebSocket.OPEN) {
            viewerWs.send(JSON.stringify({ type: "peer_left" }));
          }
        }
        // Don't destroy immediately -- give the creator a grace period to reconnect
        room.creator = null;
        room.destroyTimer = setTimeout(() => {
          if (rooms.has(currentRoom)) {
            const r = rooms.get(currentRoom);
            // Only destroy if creator never came back
            if (!r.creator || r.creator.readyState !== WebSocket.OPEN) {
              // Notify all remaining viewers that the stream has ended
              for (const [vid, viewerWs] of r.viewers) {
                if (viewerWs.readyState === WebSocket.OPEN) {
                  viewerWs.send(JSON.stringify({ type: "error", message: "Stream ended" }));
                }
              }
              r.viewers.clear();
              rooms.delete(currentRoom);
              console.log(`[Room] Destroyed after grace period: ${currentRoom}`);
            }
          }
        }, ROOM_GRACE_PERIOD_MS);
        console.log(`[Room] Creator disconnected, grace period started (${ROOM_GRACE_PERIOD_MS / 1000}s): ${currentRoom}`);
      } else if (role === "viewer") {
        // Remove this viewer from the room
        const viewerId = ws.viewerId;
        room.viewers.delete(viewerId);
        // Notify creator that this specific viewer left
        if (room.creator && room.creator.readyState === WebSocket.OPEN) {
          room.creator.send(JSON.stringify({ type: "peer_left", viewerId }));
        }
        console.log(`[Room] Viewer ${viewerId} left: ${currentRoom} (${room.viewers.size} viewer(s) remaining)`);
      }
    }
  });
});

httpServer.listen(PORT, "0.0.0.0", () => {
  console.log(`Signaling server running on http://0.0.0.0:${PORT}`);
  console.log(`Web viewer available at http://localhost:${PORT}`);
});
