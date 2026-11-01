"""Ten focused scenarios; provider/network interactions use mocks."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect

from backend.domain import (
    DraftItem,
    Extraction,
    ItemIn,
    ItemPatch,
    Meal,
    MealPlan,
    add_days,
    expiry_preview,
    inventory_context,
    level_for,
    validate_plan,
)
from backend.household import HouseholdItem, HouseholdExtraction, extract_household
from backend.llm import make_plan, parse_items
from backend.research import ResearchError, search_recipes, search_recipe_image, search_meal_images

@pytest.fixture(autouse=True)
def disable_real_notifications_during_tests(monkeypatch):
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("ENABLE_EXTERNAL_NOTIFICATIONS", "false")
    monkeypatch.setenv("ENABLE_WHATSAPP_NOTIFICATIONS", "false")


TODAY = date(2026, 11, 1)
PANTRY = [{"id": 1, "name": "milk", "expiry_date": "2026-11-03", "status": "active"}]


class FakeProvider:
    def __init__(self, response):
        self.response, self.calls = response, 0

    def generate(self, system, payload, schema):
        self.calls += 1
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def meal_plan(ingredient="milk", priorities=None):
    meal = Meal(
        dish="Simple dish",
        items_used=[ingredient, "salt"],
        steps=["Cook and serve."],
        priority_items=["milk"] if priorities is None else priorities,
    )
    return MealPlan(breakfast=meal, lunch=meal, dinner=meal)


def test_expiry_and_thresholds():
    assert add_days("2024-02-28", 2) == "2024-03-01"
    assert [level_for(d) for d in [8, 7, 6, 3, 2, 1, 0, -1]] == [
        None,
        "slight",
        "slight",
        "moderate",
        "moderate",
        "high",
        "high",
        "expired",
    ]
    original = [dict(PANTRY[0])]
    assert expiry_preview(original, date(2026, 11, 10))[0]["status"] == "expired"
    assert original[0]["status"] == "active"


def test_multiple_food_extraction_preserves_missing_information():
    provider = FakeProvider(
        Extraction(
            items=[
                DraftItem(
                    name="milk",
                    bought_date=TODAY,
                    shelf_days=5,
                    location="fridge",
                    quantity_text="one litre",
                    clarification=None,
                ),
                DraftItem(
                    name="bread",
                    bought_date=None,
                    shelf_days=None,
                    location=None,
                    quantity_text=None,
                    clarification="Missing details",
                ),
            ]
        )
    )
    result = parse_items("milk and bread", TODAY, provider)
    assert (
        len(result) == 2
        and result[1]["shelf_days"] is None
        and result[1]["bought_date"] is None
    )


def test_food_validation_and_update_state():
    valid = {
        "name": "milk",
        "bought_date": "2026-11-01",
        "shelf_days": 5,
        "location": "fridge",
    }
    assert ItemIn(**valid).name == "milk"
    for change in [
        {"shelf_days": -1},
        {"shelf_days": "5"},
        {"name": " "},
        {"location": "closet"},
    ]:
        with pytest.raises(ValidationError):
            ItemIn(**{**valid, **change})
    assert ItemPatch(status="used").status == "used"
    import main

    class ItemDB:
        def __init__(self):
            self.row = {
                "id": 1,
                "name": "milk",
                "bought_date": "2026-11-01",
                "shelf_days": 5,
                "expiry_date": "2026-11-06",
                "location": "fridge",
                "status": "active",
            }

        def table(self, _):
            return self

        def select(self, _):
            return self

        def eq(self, *_):
            return self

        def update(self, changes):
            self.row.update(changes)
            return self

        def execute(self):
            return SimpleNamespace(data=[dict(self.row)])

    db = ItemDB()
    ctx = SimpleNamespace(db=db, user_id="test")
    main.patch_item(1, ItemPatch(bought_date=date(2026, 11, 2), shelf_days=4), ctx)
    assert db.row["expiry_date"] == "2026-11-06"
    main.patch_item(1, ItemPatch(status="used"), ctx)
    assert db.row["status"] == "used"
    with pytest.raises(ValidationError):
        ItemPatch(user_id="someone")


def test_household_accepts_locations_and_tracks_time_without_expiry():
    item = HouseholdItem(name="Spare keys", category="Keys", location="Hall drawer")
    assert item.recorded_at.tzinfo and item.location == "Hall drawer"
    with pytest.raises(ValidationError):
        HouseholdItem(name="keys", category="Keys", location="")
    with pytest.raises(ValidationError):
        HouseholdItem(
            name="keys",
            category="Keys",
            location="drawer",
            recorded_at="2026-11-01T12:00:00",
        )
    draft = HouseholdExtraction.model_validate(
        {
            "items": [
                {
                    "name": "keys",
                    "category": "Keys",
                    "location": None,
                    "recorded_at": None,
                    "clarification": "Where?",
                }
            ]
        }
    )
    assert extract_household("keys", FakeProvider(draft))[0]["location"] is None


def test_priority_ingredient_and_retry():
    assert validate_plan(meal_plan(), PANTRY, ["milk"])
    provider = FakeProvider(meal_plan("chocolate", []))
    with pytest.raises(ValueError):
        make_plan(PANTRY, TODAY, provider)
    assert provider.calls == 2
    with pytest.raises(ValueError):
        validate_plan(meal_plan("milk", []), PANTRY, ["milk"])


def test_no_invented_priorities_and_meal_schema():
    future = [{**PANTRY[0], "expiry_date": "2026-11-20"}]
    result = make_plan(future, TODAY, FakeProvider(meal_plan(priorities=[])))
    assert result["priority"] == [] and result["notice"]
    assert inventory_context([{**PANTRY[0], "expiry_date": "2026-10-31"}], TODAY) == (
        [],
        [],
    )
    with pytest.raises(ValidationError):
        MealPlan.model_validate({"breakfast": meal_plan().breakfast.model_dump()})


def test_exa_sources_and_errors(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test")
    mock = Mock()
    mock.post.return_value.json.return_value = {
        "results": [
            {
                "url": "https://example.com/recipe",
                "title": "Eggs",
                "highlights": ["Cook eggs"],
            },
            {"url": "javascript:alert(1)"},
        ]
    }
    assert len(search_recipes(["eggs"], mock)) == 1
    mock.post.return_value.json.return_value = {"results": [
        {"url": "https://example.com/bad", "image": "http://localhost:8000/private"},
        {"url": "https://example.com/recipe", "title": "Omelette", "image": "https://images.example.com/omelette.jpg"},
    ]}
    image = search_recipe_image("omelette", mock)
    assert image == {"url": "https://images.example.com/omelette.jpg", "source_url": "https://example.com/recipe", "source_title": "Omelette"}
    assert mock.post.call_args.kwargs["json"]["query"] == "omelette recipe food photograph"
    mock.post.return_value.json.return_value = {"results": [
        {"url": "https://example.com/fallback", "title": "Food", "image": None, "extras": {"richImageLinks": [{"url": "https://images.example.com/logo.png"}, {"url": "https://images.example.com/dish.jpg"}]}}
    ]}
    assert search_recipe_image("omelette", mock)["url"] == "https://images.example.com/dish.jpg"
    payload = mock.post.call_args.kwargs["json"]
    assert payload["contents"]["extras"]["richImageLinks"] == 2 and payload["moderation"] is True
    from unittest.mock import patch
    with patch("backend.research.search_recipe_image", side_effect=[image, ResearchError("offline"), None]):
        results = search_meal_images({k: {"dish": k} for k in ("breakfast", "lunch", "dinner")})
    assert len(results) == 3 and sum(x is not None for x in results.values()) == 1
    # The API keeps related photos on their respective cards and avoids extra searches when research is off.
    import main
    fake_db = Mock()
    fake_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = PANTRY
    main.app.dependency_overrides[main.user_ctx] = lambda: SimpleNamespace(db=fake_db, user_id="test")
    plan = {"meals": meal_plan().model_dump(), "priority": ["milk"], "notice": None}
    try:
        with TestClient(main.app) as client, patch.object(main, "local_today", return_value=TODAY), patch.object(main, "make_plan", return_value=plan), patch.object(main, "search_recipes", return_value=[]), patch.object(main, "search_meal_images", return_value=results) as images:
            response = client.post("/api/plan/research", json={"research": True})
            assert response.status_code == 200 and response.json()["meal_images"] == results
            images.reset_mock()
            response = client.post("/api/plan/research", json={"research": False})
            assert response.status_code == 200 and response.json()["meal_images"] == {}
            images.assert_not_called()
    finally:
        main.app.dependency_overrides.clear()
    mock.post.side_effect = httpx.ConnectError("offline")
    with pytest.raises(ResearchError):
        search_recipes(["eggs"], mock)
    with pytest.raises(ResearchError):
        search_recipe_image("omelette", mock)


def test_llm_failure_propagates():
    with pytest.raises(RuntimeError):
        parse_items("milk", TODAY, FakeProvider(RuntimeError("offline")))


def test_auth_and_database_failure():
    import main
    from postgrest.exceptions import APIError
    from supabase_auth.errors import AuthWeakPasswordError, AuthRetryableError
    from unittest.mock import patch

    with TestClient(main.app) as client:
        short = client.post(
            "/signup",
            data={"name": "Test", "email": "test@example.com", "password": "abc"},
        )
        assert short.status_code == 400 and "at least 6 characters" in short.text
        auth = Mock()
        auth.auth.sign_up.side_effect = AuthWeakPasswordError(
            "Choose a stronger password.", 422, ["weak_password"]
        )
        with patch.object(main.svc, "get_db", return_value=auth):
            response = client.post(
                "/signup",
                data={
                    "name": "Test",
                    "email": "test@example.com",
                    "password": "password",
                },
            )
        assert (
            response.status_code == 400
            and "Choose a stronger password." in response.text
        )
        auth.auth.sign_in_with_password.side_effect = AuthRetryableError(
            "upstream unavailable", 503
        )
        with patch.object(main.svc, "get_db", return_value=auth):
            response = client.post(
                "/login", data={"email": "test@example.com", "password": "password"}
            )
        assert (
            response.status_code == 503 and "temporarily unavailable" in response.text
        )
        with patch.object(main.svc, "get_db", return_value=auth):
            response = client.post(
                "/resend-confirmation",
                data={"email": "test@example.com"},
                headers={"origin": "http://localhost:3000"},
            )
        assert (
            response.status_code == 200
            and "new link has been requested" in response.text
        )
        assert (
            auth.auth.resend.call_args.args[0]["options"]["email_redirect_to"]
            == "http://localhost:3000/login?confirmed=1"
        )
        with patch.dict(
            "os.environ",
            {
                "APP_ORIGIN": "",
                "CODESPACE_NAME": "test-space",
                "GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN": "app.github.dev",
            },
        ):
            assert (
                main.frontend_origin(None) == "https://test-space-3000.app.github.dev"
            )
            auth.auth.sign_up.side_effect = None
            auth.auth.sign_up.return_value = SimpleNamespace(session=None)
            with patch.object(main.svc, "get_db", return_value=auth):
                response = client.post(
                    "/signup",
                    data={
                        "name": "Test",
                        "email": "test@example.com",
                        "password": "strongpassword",
                    },
                    headers={"origin": "https://test-space-3000.app.github.dev"},
                )
            assert response.status_code == 200
            assert (
                auth.auth.sign_up.call_args.args[0]["options"]["email_redirect_to"]
                == "https://test-space-3000.app.github.dev/login?confirmed=1"
            )
        assert client.get("/api/health").status_code == 200
        assert client.get("/items").status_code == 401
        db = Mock()
        db.table.return_value.select.return_value.neq.return_value.order.return_value.execute.side_effect = APIError(
            {"code": "XX000", "message": "db down", "details": "", "hint": ""}
        )
        main.app.dependency_overrides[main.user_ctx] = lambda: SimpleNamespace(
            db=db, user_id="test"
        )
        try:
            response = client.get("/items")
            assert response.status_code == 503 and "db down" not in response.text
            db.table.return_value.select.return_value.neq.return_value.order.return_value.execute.side_effect = httpx.ConnectError(
                "offline"
            )
            assert client.get("/items").status_code == 503
        finally:
            main.app.dependency_overrides.clear()


def test_realtime_auth_and_alert_dedup_claim():
    import main
    import services

    with TestClient(main.app) as client:
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect(
                "/api/voice/stream", headers={"origin": "http://localhost:3000"}
            ):
                pass
        assert exc.value.code == 1008

        class LiveClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def post(self, path, cast_to, body):
                assert path == "/live/sessions" and cast_to == dict[str, object]
                assert body["session"]["model"] == "gpt-live-1"
                return {"transport": {"sdp": "answer"}}

        from unittest.mock import patch

        main.app.dependency_overrides[main.user_ctx] = lambda: SimpleNamespace(
            user_id="test"
        )
        try:
            with patch("backend.audio.AsyncOpenAI", LiveClient):
                response = client.post("/api/live/session", json={"sdp": "offer"})
            assert (
                response.status_code == 201
                and response.json()["transport"]["sdp"] == "answer"
            )
        finally:
            main.app.dependency_overrides.clear()

    class QueueDB:
        def __init__(self):
            self.calls = []
            self.pending = [{"id": 3, "channel": "call_mock"}]

        def rpc(self, name, params):
            self.calls.append((name, params))
            if name == "enqueue_notification_jobs":
                self.result = 1
            elif name == "claim_notification_job_v2":
                self.result = [self.pending.pop()] if self.pending else []
            elif name == "finish_notification_job":
                self.result = True
            return self

        def execute(self):
            return SimpleNamespace(data=self.result)

    from datetime import datetime, timezone

    db = QueueDB()
    with patch.object(services, "deliver_job", return_value=("sent", "Simulated call")):
        with patch.dict("os.environ", {"ENABLE_EXTERNAL_NOTIFICATIONS": "false"}):
            result = services.run_alerts(
                db, user_id="test-user", now=datetime(2026, 11, 1, tzinfo=timezone.utc)
            )
    assert result["processed"] == 1 and result["sms_enabled"] is False
    assert any(
        name == "finish_notification_job" and args["p_job_id"] == 3
        for name, args in db.calls
    )
    assert all(
        not args["p_sms_enabled"]
        for name, args in db.calls
        if name == "claim_notification_job_v2"
    )

    # The sender is only called for an eligible SMS job; the expiry-day call is simulated.
    class DeliveryDB:
        def __init__(self):
            self.table_name = None

        def table(self, name):
            self.table_name = name
            return self

        def select(self, columns):
            return self

        def eq(self, field, value):
            return self

        def execute(self):
            if self.table_name == "items":
                return SimpleNamespace(
                    data=[
                        {
                            "name": "milk",
                            "status": "active",
                            "expiry_date": "2026-11-01",
                        }
                    ]
                )
            return SimpleNamespace(data=[{"whatsapp_number": "+15555550100"}])

    job = {
        "item_id": 1,
        "user_id": "test",
        "expiry_snapshot": "2026-11-01",
        "local_day": "2026-11-01",
        "channel": "call_mock",
    }
    with patch.object(services, "TwilioClient") as twilio:
        status, message = services.deliver_job(DeliveryDB(), job)
        assert status == "sent" and "No actual call" in message
        twilio.assert_not_called()
    job["channel"] = "sms"
    with patch.dict(
        "os.environ",
        {
            "FROM_PHONE": "+15555550101",
            "TWILIO_ACCOUNT_SID": "test",
            "TWILIO_AUTH_TOKEN": "test",
        },
    ):
        with patch.object(services, "TwilioClient") as twilio:
            status, _ = services.deliver_job(DeliveryDB(), job)
            assert status == "sent"
            twilio.return_value.messages.create.assert_called_once()
            twilio.return_value.messages.create.side_effect = TimeoutError()
            assert services.deliver_job(DeliveryDB(), job)[0] == "unknown"
    job["channel"] = "whatsapp"
    with patch.dict(
        "os.environ",
        {
            "ENABLE_EXTERNAL_NOTIFICATIONS": "true",
            "ENABLE_WHATSAPP_NOTIFICATIONS": "true",
            "TWILIO_WHATSAPP_FROM": "whatsapp:+15555550101",
            "TWILIO_ACCOUNT_SID": "test",
            "TWILIO_AUTH_TOKEN": "test",
        },
    ):
        assert services.whatsapp_enabled()
        with patch.object(services, "TwilioClient") as twilio:
            assert services.deliver_job(DeliveryDB(), job)[0] == "sent"
            assert (
                twilio.return_value.messages.create.call_args.kwargs["to"]
                == "whatsapp:+15555550100"
            )
    with patch.dict(
        "os.environ",
        {
            "ENABLE_EXTERNAL_NOTIFICATIONS": "true",
            "ENABLE_WHATSAPP_NOTIFICATIONS": "false",
        },
    ):
        assert services.sms_enabled() and not services.whatsapp_enabled()
