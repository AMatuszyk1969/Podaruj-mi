"""Testy logiki rezerwacji (pledges)."""
from datetime import date, datetime, timedelta, timezone

import pytest

from tests.conftest import auth_headers, make_user


def make_occasion_and_item(client, creator, recipient, visibility="public"):
    deadline = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    occ = client.post(
        "/api/v1/occasions",
        json={
            "title": "Test okazji",
            "occasion_type": "birthday",
            "occasion_date": str(date.today() + timedelta(days=5)),
            "pledge_deadline": deadline,
            "visibility": visibility,
            "recipient_id": recipient.id,
        },
        headers=auth_headers(creator),
    ).json()

    item = client.post(
        f"/api/v1/occasions/{occ['id']}/items",
        json={"name": "Prezent testowy", "collection_mode": "single"},
        headers=auth_headers(recipient),
    ).json()

    return occ, item


class TestPledgeCreate:
    def test_giver_can_pledge(self, client, db):
        creator = make_user(db, "pl_creator1@test.pl")
        recipient = make_user(db, "pl_recipient1@test.pl")
        giver = make_user(db, "pl_giver1@test.pl")
        _, item = make_occasion_and_item(client, creator, recipient)

        resp = client.post(
            f"/api/v1/items/{item['id']}/pledge",
            json={"note": "Kupie to!"},
            headers=auth_headers(giver),
        )
        assert resp.status_code == 201
        assert resp.json()["user_id"] == giver.id

    def test_recipient_cannot_pledge_own_item(self, client, db):
        creator = make_user(db, "pl_creator2@test.pl")
        recipient = make_user(db, "pl_recipient2@test.pl")
        _, item = make_occasion_and_item(client, creator, recipient)

        resp = client.post(
            f"/api/v1/items/{item['id']}/pledge",
            json={},
            headers=auth_headers(recipient),
        )
        assert resp.status_code == 403

    def test_duplicate_pledge_rejected(self, client, db):
        creator = make_user(db, "pl_creator3@test.pl")
        recipient = make_user(db, "pl_recipient3@test.pl")
        giver = make_user(db, "pl_giver3@test.pl")
        _, item = make_occasion_and_item(client, creator, recipient)

        client.post(f"/api/v1/items/{item['id']}/pledge", json={},
                    headers=auth_headers(giver))
        resp = client.post(f"/api/v1/items/{item['id']}/pledge", json={},
                           headers=auth_headers(giver))
        assert resp.status_code == 409

    def test_item_becomes_reserved_after_single_pledge(self, client, db):
        creator = make_user(db, "pl_creator4@test.pl")
        recipient = make_user(db, "pl_recipient4@test.pl")
        giver = make_user(db, "pl_giver4@test.pl")
        occ, item = make_occasion_and_item(client, creator, recipient)

        client.post(f"/api/v1/items/{item['id']}/pledge", json={},
                    headers=auth_headers(giver))

        occ_detail = client.get(
            f"/api/v1/occasions/{occ['id']}",
            headers=auth_headers(creator),
        ).json()
        updated_item = next(i for i in occ_detail["items"] if i["id"] == item["id"])
        assert updated_item["status"] == "reserved"

    def test_second_giver_blocked_on_single_mode(self, client, db):
        creator = make_user(db, "pl_creator5@test.pl")
        recipient = make_user(db, "pl_recipient5@test.pl")
        giver1 = make_user(db, "pl_giver5a@test.pl")
        giver2 = make_user(db, "pl_giver5b@test.pl")
        _, item = make_occasion_and_item(client, creator, recipient)

        client.post(f"/api/v1/items/{item['id']}/pledge", json={},
                    headers=auth_headers(giver1))
        resp = client.post(f"/api/v1/items/{item['id']}/pledge", json={},
                           headers=auth_headers(giver2))
        assert resp.status_code == 409


class TestPledgeDelete:
    def test_giver_can_withdraw(self, client, db):
        creator = make_user(db, "wd_creator@test.pl")
        recipient = make_user(db, "wd_recipient@test.pl")
        giver = make_user(db, "wd_giver@test.pl")
        occ, item = make_occasion_and_item(client, creator, recipient)

        client.post(f"/api/v1/items/{item['id']}/pledge", json={}, headers=auth_headers(giver))
        resp = client.delete(f"/api/v1/items/{item['id']}/pledge", headers=auth_headers(giver))
        assert resp.status_code == 204

        # Item powinien wrocic do available
        occ_detail = client.get(
            f"/api/v1/occasions/{occ['id']}", headers=auth_headers(creator)
        ).json()
        updated = next(i for i in occ_detail["items"] if i["id"] == item["id"])
        assert updated["status"] == "available"

    def test_withdraw_nonexistent_pledge(self, client, db):
        creator = make_user(db, "nop_creator@test.pl")
        recipient = make_user(db, "nop_recipient@test.pl")
        giver = make_user(db, "nop_giver@test.pl")
        _, item = make_occasion_and_item(client, creator, recipient)

        resp = client.delete(f"/api/v1/items/{item['id']}/pledge", headers=auth_headers(giver))
        assert resp.status_code == 404
