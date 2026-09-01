import unittest
from unittest.mock import MagicMock, patch

from quark_storage import QuarkStorage
from scheduler import TaskScheduler


class FakeResponse:
    def __init__(self, body, status_code=200):
        self._body = body
        self.status_code = status_code

    def json(self):
        return self._body


def make_storage(signin=None, cookies=""):
    config = {
        "quark": {
            "users": {
                "account": {
                    "cookies": cookies,
                    "signin": signin or {},
                }
            },
            "current_user": "account",
        },
        "retry": {"max_attempts": 1},
    }
    save = MagicMock()
    return QuarkStorage(config, save), config, save


class QuarkSigninTests(unittest.TestCase):
    def test_extracts_credentials_from_cookie_suffix(self):
        storage, _, _ = make_storage(
            cookies="__uid=1;kps=abc%2525&sign=def&vcode=ghi"
        )

        credentials = storage._signin_credentials("account")

        self.assertEqual(
            credentials,
            {"kps": "abc%25", "sign": "def", "vcode": "ghi"},
        )

    def test_already_signed_skips_post(self):
        storage, config, save = make_storage(
            {"enabled": True, "kps": "a", "sign": "b", "vcode": "c"}
        )
        storage.session.request = MagicMock(return_value=FakeResponse({
            "data": {
                "total_capacity": 1000,
                "cap_composition": {"sign_reward": 100},
                "cap_sign": {
                    "sign_daily": True,
                    "sign_daily_reward": 20,
                    "sign_progress": 1,
                    "sign_target": 7,
                },
            }
        }))

        result = storage.run_signin("account")

        self.assertTrue(result["success"])
        self.assertTrue(result["already_signed"])
        self.assertEqual(result["reward_bytes"], 20)
        self.assertEqual(storage.session.request.call_count, 1)
        self.assertEqual(
            config["quark"]["users"]["account"]["signin_meta"]["last_status"],
            "already_signed",
        )
        save.assert_called_once()

    def test_signs_when_not_already_signed(self):
        storage, _, _ = make_storage(
            {"enabled": True, "kps": "a", "sign": "b", "vcode": "c"}
        )
        storage.session.request = MagicMock(side_effect=[
            FakeResponse({
                "data": {
                    "total_capacity": 1000,
                    "cap_composition": {"sign_reward": 100},
                    "cap_sign": {
                        "sign_daily": False,
                        "sign_progress": 2,
                        "sign_target": 7,
                    },
                }
            }),
            FakeResponse({"data": {"sign_daily_reward": 50}}),
        ])

        result = storage.run_signin("account")

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "signed")
        self.assertEqual(result["reward_bytes"], 50)
        self.assertEqual(result["sign_progress"], 3)
        self.assertEqual(storage.session.request.call_count, 2)

    def test_marks_401_as_expired_without_retry(self):
        storage, _, _ = make_storage(
            {"enabled": True, "kps": "a", "sign": "b", "vcode": "c"}
        )
        storage.session.request = MagicMock(
            return_value=FakeResponse({"code": 50051, "message": "invalid"}, 401)
        )

        result = storage.run_signin("account")

        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "credentials_expired")
        self.assertEqual(storage.session.request.call_count, 1)

    @patch("quark_storage.time.sleep")
    def test_retries_transient_server_error(self, _sleep):
        storage, _, _ = make_storage(
            {"enabled": True, "kps": "a", "sign": "b", "vcode": "c"}
        )
        storage.config["retry"]["max_attempts"] = 2
        storage.session.request = MagicMock(side_effect=[
            FakeResponse({"message": "busy"}, 503),
            FakeResponse({
                "data": {
                    "cap_sign": {
                        "sign_daily": True,
                        "sign_daily_reward": 10,
                    }
                }
            }),
        ])

        result = storage.run_signin("account")

        self.assertTrue(result["success"])
        self.assertEqual(storage.session.request.call_count, 2)


class SchedulerSystemJobTests(unittest.TestCase):
    @patch("scheduler.BackgroundScheduler")
    def test_system_jobs_register_without_transfer_tasks(self, scheduler_factory):
        instance = TaskScheduler.__new__(TaskScheduler)
        instance.scheduler = None
        instance.is_running = False
        instance.storage = MagicMock()
        instance.storage.config = {
            "scheduler": {},
            "cron": {"default_schedule": []},
        }
        instance._get_current_tasks = MagicMock(return_value=[])
        instance._add_quota_check_job = MagicMock()
        instance._add_quark_signin_job = MagicMock()
        scheduler_factory.return_value = MagicMock()

        instance._init_scheduler()

        instance._add_quota_check_job.assert_called_once()
        instance._add_quark_signin_job.assert_called_once()

    def test_update_tasks_restores_system_jobs(self):
        instance = TaskScheduler.__new__(TaskScheduler)
        instance.scheduler = MagicMock()
        instance.storage = MagicMock()
        instance.storage.list_tasks.return_value = []
        instance._add_quota_check_job = MagicMock()
        instance._add_quark_signin_job = MagicMock()

        instance.update_tasks()

        instance.scheduler.remove_all_jobs.assert_called_once()
        instance._add_quota_check_job.assert_called_once()
        instance._add_quark_signin_job.assert_called_once()


class MultiAccountTests(unittest.TestCase):
    def test_enabled_accounts_are_isolated(self):
        config = {
            "quark": {
                "users": {
                    "first": {"cookies": "", "signin": {"enabled": True}},
                    "second": {"cookies": "", "signin": {"enabled": False}},
                    "third": {"cookies": "", "signin": {"enabled": True}},
                },
                "current_user": "first",
            },
        }
        storage = QuarkStorage(config)
        storage.run_signin = MagicMock(side_effect=[
            {"account": "first", "success": False},
            {"account": "third", "success": True},
        ])

        results = storage.run_enabled_signins()

        self.assertEqual([result["account"] for result in results], ["first", "third"])
        self.assertEqual(storage.run_signin.call_count, 2)


if __name__ == "__main__":
    unittest.main()
