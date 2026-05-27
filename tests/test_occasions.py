"""Testy okazji i zychen."""
from datetime import date, datetime, timedelta, timezone

import pytest

from tests.conftest import auth_headers, make_user


def future_deadline():
    return (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()


def occasion_payload(recipient_id: str, visibility: str = "friends") -> dict:
    return {
        "title": "Urodziny Jana",
        "occasion_type": "birthday",
        "occasion_date": str(date.today() + timedelta(days=7)),
        "pledge_deadline": future_deadline(),
        "visibility": visibility,
        "recipient_id": recipient_id,
    }


class TestOccasionCRUD:
    def test_create_occasion(self, client, db):
        creator = make_user(db, "creator_occ@test.pl")
        recipient = make_user(db, "recipient_occ@test.pl")

        resp = client.post(
            "/api/v1/occasions",
            json=occasion_payload(recipient.id),
            headers=auth_headers(creator),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Urodziny Jana"
        assert data["recipient"]["id"] == recipient.id

    def test_create_occasion_invalid_deadline(self, client, db):
        creator = make_user(db, "creator_dl@test.pl")
        recipient = make_user(db, "recipient_dl@test.pl")
        payload = occasion_payload(recipient.id)
        payload["pledge_deadline"] = (
            datetime.now(timezone.utc) + timedelta(days=30)
        ).isoformat()  # deadline PO okazji

        resp = client.post(
            "/api/v1/occasions",
            json=payload,
            headers=auth_headers(creator),
        )
        assert resp.status_code == 422

    def test_get_occasion_as_creator(self, client, db):
        creator = make_user(db, "get_creator@test.pl")
        recipient = make_user(db, "get_recipient@test.pl")
        created = client.post(
            "/api/v1/occasions",
            json=occasion_payload(recipient.id),
            headers=auth_headers(creator),
        ).json()

        resp = client.get(f"/api/v1/occasions/{created['id']}", headers=auth_headers(creator))
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    def test_get_occasion_no_access(self, client, db):
        creator = make_user(db, "noacc_creator@test.pl")
        recipient = make_user(db, "noacc_recipient@test.pl")
        stranger = make_user(db, "stranger_occ@test.pl")

        created = client.post(
            "/api/v1/occasions",
            json=occasion_payload(recipient.id, visibility="friends"),
            headers=auth_headers(creator),
        ).json()

        # Stranger nie jest znajomym – visibility=friends
        resp = client.get(f"/api/v1/occasions/{created['id']}", headers=auth_headers(stranger))
        assert resp.status_code == 403

    def test_delete_occasion_with_no_pledges(self, client, db):
        creator = make_user(db, "del_occ_creator@test.pl")
        recipient = make_user(db, "del_occ_recipient@test.pl")
        created = client.post(
            "/api/v1/occasions",
            json=occasion_payload(recipient.id),
            headers=auth_headers(creator),
        ).json()

        resp = client.delete(f"/api/v1/occasions/{created['id']}", headers=auth_headers(creator))
        assert resp.status_code == 204


class TestItems:
    def _create_occasion(self, client, creator, recipient):
        return client.post(
            "/api/v1/occasions",
            json=occasion_payload(recipient.id),
            headers=auth_headers(creator),
        ).json()

    def test_add_item_as_recipient(self, client, db):
        creator = make_user(db, "item_creator@test.pl")
        recipient = make_user(db, "item_recipient@test.pl")
        occ = self._create_occasion(client, creator, recipient)

        resp = client.post(
            f"/api/v1/occasions/{occ['id']}/items",
            json={"name": "Ksiazka", "url": "https://example.com", "estimated_price": "49.99"},
            headers=auth_headers(recipient),
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "Ksiazka"

    def test_add_item_as_stranger_forbidden(self, client, db):
        creator = make_user(db, "item_str_creator@test.pl")
        recipient = make_user(db, "item_str_recipient@test.pl")
        stranger = make_user(db, "item_str_stranger@test.pl")
        occ = self._create_occasion(client, creator, recipient)

        resp = client.post(
            f"/api/v1/occasions/{occ['id']}/items",
            json={"name": "Niespodzianka"},
            headers=auth_headers(stranger),
        )
        assert resp.status_code == 403

    def test_recipient_cannot_see_pledges(self, client, db):
        creator = make_user(db, "priv_creator@test.pl")
        recipient = make_user(db, "priv_recipient@test.pl")
        giver = make_user(db, "priv_giver@test.pl")
        occ = self._create_occasion(client, creator, recipient)

        item_resp = client.post(
            f"/api/v1/occasions/{occ['id']}/items",
            json={"name": "Tajny prezent"},
            headers=auth_headers(recipient),
        ).json()

        # Giver rezerwuje – musimy dac mu dostep przez publiczna widocznosc
        # Zmienmy okazje na public (przez edycje)
        client.patch(
            f"/api/v1/occasions/{occ['id']}",
            json={"visibility": "public"},
            headers=auth_headers(creator),
        )
        client.post(
            f"/api/v1/items/{item_resp['id']}/pledge",
            json={},
            headers=auth_headers(giver),
        )

        # Obdarowywany NIE powinien widziec pledges
        occ_detail = client.get(
            f"/api/v1/occasions/{occ['id']}",
            headers=auth_headers(recipient),
        ).json()
        item = next(i for i in occ_detail["items"] if i["id"] == item_resp["id"])
        assert item["pledges"] == []
        assert item["pledges_count"] == 1  # ale count jest widoczny
