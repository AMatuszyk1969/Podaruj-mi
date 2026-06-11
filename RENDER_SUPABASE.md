# Wdrożenie: Render.com + Supabase

Instrukcja krok po kroku. **Render** hostuje aplikację (Docker), **Supabase**
dostarcza bazę PostgreSQL i Storage na avatary.

Czas: ~30–45 min. Wymaga konta na [Supabase](https://supabase.com),
[Render](https://render.com) i dostawcy e-mail ([Brevo](https://www.brevo.com)).

---

## Krok 1 — Supabase: projekt i baza

1. Załóż projekt w Supabase. **Region: Central EU (Frankfurt)** — RODO + niskie opóźnienia w PL.
2. Zapisz hasło bazy ustawione przy tworzeniu projektu.
3. Pobierz connection string: **Project Settings → Database → Connection string**.

   ⚠️ Wybierz **„Session pooler”** (nie „Direct connection”). Bezpośrednie połączenie
   Supabase jest dziś IPv6-only i **nie zadziała z Render** (IPv4). Session pooler jest
   IPv4 i wspiera migracje Alembic. (Nie używaj „Transaction pooler”/port 6543 —
   nie obsługuje migracji.)

4. String wygląda mniej więcej tak:
   ```
   postgresql://postgres.<PROJECT_REF>:<HASLO>@aws-0-eu-central-1.pooler.supabase.com:5432/postgres
   ```
   Przerób go na format SQLAlchemy + wymuś SSL — to wartość `DATABASE_URL`:
   ```
   postgresql+psycopg2://postgres.<PROJECT_REF>:<HASLO>@aws-0-eu-central-1.pooler.supabase.com:5432/postgres?sslmode=require
   ```

---

## Krok 2 — Supabase: Storage na avatary

1. **Storage → New bucket** → nazwa: `avatars`.
2. Zaznacz **Public bucket** (publiczne URL-e zdjęć).
3. Pobierz dane z **Project Settings → API**:
   - `SUPABASE_URL` = „Project URL” (np. `https://<PROJECT_REF>.supabase.co`)
   - `SUPABASE_KEY` = klucz **`service_role`** (ma prawo zapisu do bucketu).
     ⚠️ Trzymaj go w sekretach — używany tylko po stronie serwera.
   - `SUPABASE_BUCKET` = `avatars`

---

## Krok 3 — E-mail (Brevo)

1. Załóż konto na [Brevo](https://www.brevo.com) (dawniej Sendinblue) — firma z UE,
   RODO-friendly, darmowy plan 300 maili/dzień.
2. Zweryfikuj domenę nadawcy: **Senders, Domains & Dedicated IPs → Domains** —
   ustaw rekordy **SPF/DKIM** (Brevo poda gotowe wpisy DNS), dodaj **DMARC** (`p=none` na start).
3. Pobierz dane SMTP: **SMTP & API → SMTP** — tam jest host, login i klucz SMTP.
4. Wartości środowiskowe:
   ```
   MAIL_USERNAME = <e-mail konta Brevo>
   MAIL_PASSWORD = <klucz SMTP z Brevo>
   MAIL_FROM     = noreply@twoja-domena.pl
   MAIL_SERVER   = smtp-relay.brevo.com
   MAIL_PORT     = 587
   MAIL_STARTTLS = true
   MAIL_SSL_TLS  = false
   ```
> Bez SPF/DKIM maile aktywacyjne trafią do spamu. Przetestuj na mail-tester.com.
> Alternatywa o podobnej konfiguracji: Resend (`smtp.resend.com`, login `resend`,
> hasło = API key).

---

## Krok 4 — Sentry (monitoring)

1. Załóż projekt na [sentry.io](https://sentry.io), skopiuj **DSN**.
2. `SENTRY_DSN` = wklejony DSN. (`SENTRY_TRACES_SAMPLE_RATE` jest już ustawione na `0.1`.)

---

## Krok 5 — Render: utworzenie serwisu z Blueprintu

1. Wypchnij kod na GitHub (repo zawiera `render.yaml` i `Dockerfile`).
2. W Render: **New → Blueprint** → wskaż repozytorium. Render odczyta `render.yaml`
   i utworzy web service `podaruj-mi` (Docker, region Frankfurt, health check `/health`).
3. Render poprosi o wartości zmiennych oznaczonych `sync: false`. Uzupełnij:

   | Zmienna | Wartość |
   |---|---|
   | `DATABASE_URL` | string z Kroku 1 (Session pooler + `?sslmode=require`) |
   | `FRONTEND_URL` | `https://podaruj-mi.onrender.com` *(patrz uwaga niżej)* |
   | `MAIL_*` | z Kroku 3 |
   | `SUPABASE_URL` / `SUPABASE_KEY` / `SUPABASE_BUCKET` | z Kroku 2 |
   | `SENTRY_DSN` | z Kroku 4 |

   `SECRET_KEY` wygeneruje się automatycznie. `APP_ENV=production` itd. są już w `render.yaml`.

   > **Uwaga o `FRONTEND_URL`**: to publiczny adres serwisu. Jeśli nazwa serwisu to
   > `podaruj-mi`, URL będzie `https://podaruj-mi.onrender.com` — możesz ustawić od razu.
   > Jeśli nie masz pewności, ustaw po pierwszym deployu (Render pokaże URL) i kliknij
   > **Manual Deploy → Deploy latest commit**.

4. Kliknij **Apply** / **Create**. Render zbuduje obraz, wykona `alembic upgrade head`
   i wystartuje aplikację. Pierwszy build trwa kilka minut.

> **Plan**: `render.yaml` ustawia `starter` (~$7/mc), bo plan `free` usypia serwis po
> 15 min bezczynności — wtedy **scheduler przestaje działać** (przypomnienia/podsumowania
> nie wyjdą) i pojawiają się zimne starty. Na produkcję zostań przy `starter`.

---

## Krok 6 — Po wdrożeniu

- [ ] Otwórz `https://<twój-serwis>.onrender.com/health` → `{"status":"ok"}`.
- [ ] Upewnij się, że `FRONTEND_URL` = realny URL serwisu (inaczej linki w mailach będą złe). Po zmianie → redeploy.
- [ ] Smoke test (z DEPLOYMENT.md §13): rejestracja → mail aktywacyjny (link `https://`) →
      logowanie → okazja → upload avatara (ląduje w Supabase) → reset hasła → usunięcie konta.
- [ ] W Sentry: wywołaj kontrolowany błąd i sprawdź, że zdarzenie dotarło; skonfiguruj alert.
- [ ] Podepnij `GET /health` pod monitor uptime (UptimeRobot / Better Stack).
- [ ] (Opcjonalnie) Własna domena: Render → Settings → Custom Domains → dodaj rekordy DNS.
      Po zmianie domeny zaktualizuj `FRONTEND_URL` i `MAIL_FROM`.

---

## Najczęstsze problemy

| Objaw | Przyczyna / rozwiązanie |
|---|---|
| Build/Start pada na połączeniu z bazą | Użyto „Direct connection” (IPv6) — przełącz na **Session pooler** (Krok 1). |
| `alembic` błędy / dziwne zachowanie zapytań | Użyto „Transaction pooler” (6543) — użyj **Session** (5432). |
| Linki w mailach są `http://` zamiast `https://` | Brak `--proxy-headers` (jest już w `Dockerfile`) lub złe `FRONTEND_URL`. |
| Logowanie nie utrzymuje sesji | Serwis nie na HTTPS lub `APP_ENV` ≠ `production`. Render daje HTTPS automatycznie. |
| Avatary znikają po redeployu | `SUPABASE_*` nieustawione — apka zapisała lokalnie (efemeryczny dysk). |
| Maile w spamie | Brak SPF/DKIM/DMARC na domenie nadawcy (Krok 3). |
| Przypomnienia nie wychodzą | Plan `free` (usypianie) — przejdź na `starter`. |

---

> Połączenie z ogólną checklistą produkcyjną: **DEPLOYMENT.md**.
