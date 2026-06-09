# Wdrożenie produkcyjne — „Podaruj mi”

Checklista i instrukcja uruchomienia aplikacji na produkcji. Dokument zakłada
wdrożenie w kontenerach (Docker) za reverse proxy z TLS.

> ⚠️ **Nie używaj `docker-compose.yml` z repo na produkcji** — zawiera MailHoga,
> tryb `--reload` i deweloperski `SECRET_KEY`. Służy wyłącznie do dev.

---

## 1. Architektura w skrócie

- **Aplikacja**: FastAPI + Jinja2 + HTMX (renderowanie po stronie serwera).
- **Baza**: PostgreSQL, migracje przez Alembic (`alembic upgrade head`).
- **E-mail**: fastapi-mail (SMTP, np. SendGrid) — aktywacja konta, reset hasła,
  powiadomienia o okazjach i terminach.
- **Pliki (avatary)**: Supabase Storage (lub lokalny dysk w dev).
- **Zadania w tle**: APScheduler w procesie aplikacji (przypomnienia, podsumowania).
- **Monitoring**: Sentry (błędy), endpoint `GET /health` (uptime).
- **Sesja**: JWT w ciasteczku `pm_token` (httponly), ochrona CSRF `pm_csrf`.

---

## 2. Checklista przed startem (must-have)

### Bezpieczeństwo / konfiguracja
- [ ] `APP_ENV=production` (włącza `secure` na ciasteczkach, wyłącza `/docs`).
- [ ] `SECRET_KEY` = losowy ciąg ≥ 32 znaki: `python -c "import secrets; print(secrets.token_hex(32))"`.
- [ ] `FRONTEND_URL` = publiczny adres HTTPS aplikacji (używany w CORS).
- [ ] Aplikacja serwowana **wyłącznie przez HTTPS** (patrz §6) — bez tego logowanie nie zadziała (ciasteczka `secure`).
- [ ] Uvicorn z `--proxy-headers --forwarded-allow-ips="*"` (patrz §6) — inaczej linki w mailach i URL-e avatarów będą `http://`.

### Dane / trwałość
- [ ] PostgreSQL na osobnym, trwałym wolumenie + **automatyczne backupy** (§10).
- [ ] `alembic upgrade head` wykonane na docelowej bazie (§5).
- [ ] Supabase Storage skonfigurowane (§8) — inaczej avatary znikają po redeployu.

### Komunikacja
- [ ] Produkcyjny SMTP (np. SendGrid) + **SPF / DKIM / DMARC** na domenie (§7).
- [ ] Adres `MAIL_FROM` na zweryfikowanej domenie.

### Prawne (RODO) — przed publicznym startem
- [ ] Treść `Regulamin` (`/regulamin`) uzupełniona przez prawnika.
- [ ] Treść `Polityka prywatności` (`/polityka-prywatnosci`) uzupełniona (dane administratora, procesorzy, retencja).
- [ ] Umowy powierzenia danych z procesorami (SendGrid, Supabase, hosting).

### Monitoring
- [ ] `SENTRY_DSN` ustawiony, alerty skonfigurowane w panelu Sentry (§9).
- [ ] Monitor uptime pingujący `GET /health` (§9).

---

## 3. Zmienne środowiskowe (produkcja)

Skopiuj `.env.example` → `.env` i ustaw wartości produkcyjne:

```env
APP_ENV=production
APP_NAME="Podaruj mi"
APP_VERSION=1.0.0
FRONTEND_URL=https://twoja-domena.pl

DATABASE_URL=postgresql+psycopg2://USER:HASLO@HOST:5432/podaruj_mi

SECRET_KEY=<wygenerowany losowy hex 32+ znaki>
ACCESS_TOKEN_EXPIRE_MINUTES=43200

# E-mail (SendGrid lub inny SMTP)
MAIL_USERNAME=apikey
MAIL_PASSWORD=<sendgrid_api_key>
MAIL_FROM=noreply@twoja-domena.pl
MAIL_SERVER=smtp.sendgrid.net
MAIL_PORT=587
MAIL_STARTTLS=true
MAIL_SSL_TLS=false

# Supabase Storage (avatary)
SUPABASE_URL=https://twoj-projekt.supabase.co
SUPABASE_KEY=<service_role_lub_klucz_z_uprawnieniem_zapisu_do_bucketu>
SUPABASE_BUCKET=avatars

# Monitoring
LOG_LEVEL=INFO
SENTRY_DSN=https://...@oXXX.ingest.sentry.io/YYY
SENTRY_TRACES_SAMPLE_RATE=0.1

# Rate limiting
LOGIN_RATE_LIMIT=5/minute
GENERAL_RATE_LIMIT=100/minute
```

> `SECRET_KEY` jest wymagany (brak wartości = aplikacja się nie uruchomi).
> Trzymaj `.env` poza repo i poza obrazem (np. sekrety platformy hostingowej).

---

## 4. Uruchomienie (Docker)

Obraz buduje się z istniejącego `Dockerfile` (uruchamia jako użytkownik
`appuser`, robi `alembic upgrade head`, startuje uvicorn).

Dla produkcji nadpisz `command`, dodając obsługę nagłówków proxy i **bez** `--reload`:

```yaml
# docker-compose.prod.yml (przykład – bez MailHoga)
services:
  app:
    build: .
    restart: always
    env_file: .env
    command: >
      sh -c "alembic upgrade head &&
             uvicorn app.main:app --host 0.0.0.0 --port 8000
             --proxy-headers --forwarded-allow-ips='*'"
    depends_on:
      db:
        condition: service_healthy

  db:
    image: postgres:16-alpine
    restart: always
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: podaruj_mi
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d podaruj_mi"]
      interval: 5s
      timeout: 5s
      retries: 10

volumes:
  pgdata:
```

```bash
docker compose -f docker-compose.prod.yml up --build -d
```

> **Uruchamiaj tylko 1 instancję aplikacji** (patrz §11 — scheduler i rate limiter).

---

## 5. Baza danych i migracje

- Migracje są wykonywane automatycznie przy starcie (`alembic upgrade head` w `command`).
- Ręcznie: `docker compose -f docker-compose.prod.yml exec app alembic upgrade head`.
- Historia migracji: katalog `alembic/versions/` (m.in. `family_id`, `summary_sent`).
- **Nie** polegaj na `Base.metadata.create_all` jako mechanizmie migracji — to tylko
  zabezpieczenie dla świeżej bazy; źródłem prawdy jest Alembic.

---

## 6. HTTPS i reverse proxy

Aplikacja ustawia ciasteczka z flagą `secure` w produkcji — **wymaga HTTPS**.
Dodatkowo URL-e w mailach i ścieżki avatarów budowane są z `request.base_url`,
więc proxy musi przekazywać `X-Forwarded-Proto`, a uvicorn musi mu ufać
(`--proxy-headers --forwarded-allow-ips`).

Przykład (Caddy — automatyczny TLS):

```
twoja-domena.pl {
    reverse_proxy app:8000
}
```

Przykład (nginx — fragment):

```nginx
location / {
    proxy_pass http://app:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;   # kluczowe dla https w mailach
}
```

Weryfikacja: po wdrożeniu zarejestruj testowe konto i sprawdź, że link
aktywacyjny w mailu zaczyna się od `https://`.

---

## 7. Dostarczalność e-maili (SPF / DKIM / DMARC)

Bez tego maile aktywacyjne i resetu hasła trafią do spamu → użytkownicy nie założą konta.

- [ ] Zweryfikuj domenę nadawcy u dostawcy SMTP (np. SendGrid → Sender Authentication).
- [ ] Dodaj rekordy **SPF**, **DKIM** (zwykle CNAME-y od dostawcy) w DNS domeny.
- [ ] Dodaj rekord **DMARC** (`_dmarc.twoja-domena.pl`), zacznij od `p=none`.
- [ ] Przetestuj na [mail-tester.com](https://www.mail-tester.com) (cel: 9–10/10).

---

## 8. Przechowywanie avatarów (Supabase)

- [ ] Utwórz bucket `avatars` w Supabase Storage.
- [ ] Ustaw bucket jako **public** (URL-e avatarów są publiczne) lub dostosuj politykę.
- [ ] Ustaw `SUPABASE_URL`, `SUPABASE_KEY` (z prawem zapisu), `SUPABASE_BUCKET`.

Kod automatycznie użyje Supabase, gdy te zmienne są ustawione; w przeciwnym razie
zapisuje lokalnie (tylko dev). Stary avatar jest kasowany przy podmianie.

---

## 9. Monitoring i alerty

**Sentry (błędy):**
- [ ] Załóż projekt na sentry.io, wklej `SENTRY_DSN` do `.env`.
- [ ] `SENTRY_TRACES_SAMPLE_RATE=0.1` (10% żądań z tracingiem wydajności).
- [ ] Skonfiguruj alerty: *Alerts → np. e-mail/Slack przy nowym błędzie lub gdy
  >N błędów / 5 min*. Przechwytywane są nieobsłużone wyjątki oraz logi `ERROR`
  (w tym błędy zadań w tle, z pełnym tracebackiem).

**Uptime (dostępność):**
- [ ] Podepnij `GET /health` pod zewnętrzny monitor (UptimeRobot, Better Stack)
  — ping co 1–5 min, alert przy niedostępności. Sentry nie wykryje „leżącego” serwera.

---

## 10. Kopie zapasowe

- [ ] Automatyczny backup PostgreSQL (codziennie). Przykład:
  `pg_dump -U USER podaruj_mi | gzip > backup_$(date +%F).sql.gz`.
- [ ] Przetestuj **odtworzenie** z backupu (backup bez testu restore = brak backupu).
- [ ] Retencja zgodna z polityką (np. 7 dziennych + 4 tygodniowe).
- [ ] Avatary w Supabase mają własną trwałość; rozważ politykę wersjonowania bucketu.

---

## 11. Skalowanie — ważne ograniczenia

Aplikacja w obecnej formie zakłada **jedną instancję**:

- **Scheduler (APScheduler)** działa w procesie aplikacji. Przy >1 instancji
  przypomnienia i podsumowania wyślą się **wielokrotnie**. Przy skalowaniu poziomym
  wydziel scheduler do osobnego, pojedynczego procesu albo użyj blokady rozproszonej.
- **Rate limiter (slowapi)** trzyma liczniki w pamięci procesu — przy wielu
  instancjach limity są per-instancja. Do skalowania podłącz backend Redis.

Dla MVP: 1 instancja aplikacji + pionowe skalowanie w zupełności wystarczą.

---

## 12. Checklista bezpieczeństwa

- [ ] `APP_ENV=production` (wyłączone `/docs`, `/redoc`; ciasteczka `secure`).
- [ ] Silny, unikalny `SECRET_KEY` (nie z repo/dev).
- [ ] HTTPS wymuszony, przekierowanie z http→https na proxy.
- [ ] Hasła bazy i klucze API trzymane w sekretach platformy, nie w repo.
- [ ] CSRF aktywny (wbudowany middleware) — obejmuje też upload plików.
- [ ] Rate limiting na logowaniu i ogólny — wartości w `.env`.
- [ ] Regularne aktualizacje zależności (`poetry update`, przegląd CVE).

---

## 13. Testy po wdrożeniu (smoke test)

- [ ] `GET /health` → `200`.
- [ ] Rejestracja → mail aktywacyjny dociera (link `https://`), aktywacja działa.
- [ ] Logowanie / wylogowanie.
- [ ] Utworzenie okazji, dodanie życzenia, rezerwacja przez innego użytkownika.
- [ ] Upload avatara → plik ląduje w Supabase, widoczny po odświeżeniu.
- [ ] Reset hasła → mail dociera, zmiana działa.
- [ ] Usunięcie konta → konto i powiązane dane znikają.
- [ ] Wywołaj kontrolowany błąd i sprawdź, że pojawił się w Sentry.
- [ ] Strony `/regulamin` i `/polityka-prywatnosci` otwierają się publicznie.

---

## 14. Status gotowości (na dziś)

| Obszar | Status |
|---|---|
| Funkcje produktu | ✅ Kompletne |
| Usuwanie konta (RODO) | ✅ Wdrożone |
| Trwałość avatarów (Supabase) | ✅ Kod gotowy — wymaga konfiguracji bucketu |
| Monitoring (Sentry + /health) | ✅ Kod gotowy — wymaga DSN + monitora uptime |
| Strony prawne | ⚠️ Szkielet — treść do uzupełnienia przez prawnika |
| Sekrety / SMTP / HTTPS | ⚠️ Konfiguracja po stronie wdrożenia (ten dokument) |

---

> Dokument opisuje stan kodu z gałęzi `main`. Aktualizuj go przy zmianach
> architektury (np. wydzielenie schedulera, dodanie Redis, CDN dla statyków).
