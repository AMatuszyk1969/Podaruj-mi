// Service Worker – Podaruj mi PWA
const CACHE = "pm-v1";

// Zasoby do wstępnego zbuforowania
const PRECACHE = [
  "/",
  "/login",
  "/static/manifest.json",
];

// ── Install ───────────────────────────────────────────────────────────────────
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(PRECACHE))
  );
  self.skipWaiting();
});

// ── Activate ──────────────────────────────────────────────────────────────────
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// ── Fetch – Network-first, fallback to cache ──────────────────────────────────
self.addEventListener("fetch", (event) => {
  // Tylko GET; wszystkie POST/DELETE/PUT przepuszczamy bez cache
  if (event.request.method !== "GET") return;

  // Pomijamy żądania do zewnętrznych CDN (HTMX, Tailwind)
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // Buforuj udane odpowiedzi dla stron i plików statycznych
        if (
          response.ok &&
          (url.pathname.startsWith("/static/") ||
            url.pathname === "/" ||
            url.pathname === "/login")
        ) {
          const clone = response.clone();
          caches.open(CACHE).then((cache) => cache.put(event.request, clone));
        }
        return response;
      })
      .catch(() => {
        // Sieć niedostępna – serwuj z cache
        return caches.match(event.request).then(
          (cached) => cached || new Response("<h1>Brak połączenia</h1>", {
            headers: { "Content-Type": "text/html" },
          })
        );
      })
  );
});
