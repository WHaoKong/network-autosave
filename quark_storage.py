import posixpath
import random
import re
import time
from datetime import datetime
from threading import Lock
from urllib.parse import parse_qs, urlparse

import requests
from loguru import logger


class QuarkSigninError(RuntimeError):
    def __init__(self, message, code=None, http_status=None, expired=False, transient=False):
        super().__init__(message)
        self.code = code
        self.http_status = http_status
        self.expired = expired
        self.transient = transient


class QuarkStorage:
    SIGNIN_BASE_URL = "https://drive-m.quark.cn/1/clouddrive/capacity/growth"
    SERVICE_CONFIGS = {
        "quark": {
            "base_url": "https://drive-pc.quark.cn/1/clouddrive",
            "save_url": "https://drive.quark.cn/1/clouddrive/share/sharepage/save",
            "referer": "https://pan.quark.cn/",
            "origin": "https://pan.quark.cn",
            "pr": "ucpro",
            "share_host": "pan.quark.cn",
            "detail_path": "/share/sharepage/detail",
            "label": "\u5938\u514b",
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        },
        "uc": {
            "base_url": "https://pc-api.uc.cn/1/clouddrive",
            "save_url": "https://pc-api.uc.cn/1/clouddrive/share/sharepage/save",
            "referer": "https://drive.uc.cn/",
            "origin": "https://drive.uc.cn",
            "pr": "UCBrowser",
            "share_host": "drive.uc.cn",
            "detail_path": "/transfer_share/detail",
            "label": "UC",
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "uc-cloud-drive/2.5.20 Chrome/100.0.4896.160 "
                "Electron/18.3.5.4-b478491100 Safari/537.36 Channel/pckk_other_ch"
            ),
        },
    }

    def __init__(self, config, save_config_callback=None, provider="quark"):
        self.config = config
        self._save_config_callback = save_config_callback
        self.provider = provider
        self.service = self.SERVICE_CONFIGS[provider]
        self.session = requests.Session()
        self._signin_lock = Lock()
        self._ensure_config()

    def _ensure_config(self):
        provider_config = self.config.setdefault(self.provider, {})
        provider_config.setdefault("users", {})
        provider_config.setdefault("current_user", None)
        if self.provider == "quark":
            self.config.setdefault("quark_signin", {
                "enabled": False,
                "schedule": "0 8 * * *",
                "notify": True,
            })
            for user in provider_config["users"].values():
                signin = user.setdefault("signin", {})
                signin.setdefault("enabled", False)
                signin.setdefault("kps", "")
                signin.setdefault("sign", "")
                signin.setdefault("vcode", "")

    def _save_config(self):
        if self._save_config_callback:
            try:
                self._save_config_callback(update_scheduler=False)
            except TypeError:
                self._save_config_callback()

    def _current_cookie(self, account=None):
        current_user = account or self.config.get(self.provider, {}).get("current_user")
        if not current_user:
            return None, "\u5206\u4eab\u4e2d\u6ca1\u6709\u53ef\u8f6c\u5b58\u7684\u6587\u4ef6"

        user_info = self.config.get(self.provider, {}).get("users", {}).get(current_user)
        if not user_info or not user_info.get("cookies"):
            return None, f"{self.provider} user {current_user} is invalid"

        return user_info["cookies"], None

    def _headers(self, cookie=None):
        if cookie is None:
            cookie, _ = self._current_cookie()

        return {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Cookie": cookie or "",
            "Origin": self.service["origin"],
            "Referer": self.service["referer"],
            "User-Agent": self.service["user_agent"],
            "x-biz-retry": "0",
        }

    def _params(self, extra=None):
        params = {
            "pr": self.service["pr"],
            "fr": "pc",
            "uc_param_str": "",
            "__dt": random.randint(600, 9999),
            "__t": int(time.time() * 1000),
        }
        if self.provider == "uc":
            params["entry"] = "ft"
        if extra:
            params.update(extra)
        return params

    def _request(self, method, url, **kwargs):
        response = self.session.request(method, url, timeout=30, **kwargs)
        response.raise_for_status()
        data = response.json()

        status = data.get("status")
        code = data.get("code")
        if status not in (None, 0, 200) and data.get("message"):
            raise RuntimeError(data.get("message"))
        if code not in (None, 0):
            raise RuntimeError(data.get("message") or data.get("error") or data)

        return data

    def _extract_pwd_id(self, share_url):
        parsed = urlparse(share_url.split("#")[0])
        if self.service["share_host"] not in parsed.netloc:
            raise ValueError("\u5206\u4eab\u4e2d\u6ca1\u6709\u53ef\u8f6c\u5b58\u7684\u6587\u4ef6")

        match = re.search(r"/s/([A-Za-z0-9_-]+)", parsed.path)
        if match:
            return match.group(1)

        params = parse_qs(parsed.query)
        for key in ("pwd_id", "share_id"):
            if params.get(key):
                return params[key][0]

        raise ValueError("\u65e0\u6cd5\u89e3\u6790\u5938\u514b\u5206\u4eab ID")

    def _extract_passcode(self, share_url, pwd=None):
        if pwd:
            return pwd

        parsed = urlparse(share_url.split("#")[0])
        params = parse_qs(parsed.query)
        for key in ("pwd", "passcode", "password"):
            if params.get(key):
                return params[key][0]

        return ""

    def validate_cookie(self, cookies):
        try:
            data = self._request(
                "GET",
                f"{self.service['base_url']}/member",
                headers=self._headers(cookies),
                params=self._params(),
            )
            return data.get("data") is not None
        except Exception as exc:
            logger.warning(f"\u5938\u514b Cookies \u6821\u9a8c\u5931\u8d25: {exc}")
            return False

    def get_quota(self, account=None):
        cookie, error = self._current_cookie(account)
        if error:
            return None
        try:
            data = self._request(
                "GET",
                f"{self.service['base_url']}/member",
                headers=self._headers(cookie),
                params=self._params(),
            )
            payload = data.get("data") or {}
            return {
                "total": int(payload.get("total_capacity") or 0),
                "used": int(payload.get("use_capacity") or 0),
            }
        except Exception as exc:
            logger.warning(f"{self.service['label']} quota fetch failed: {exc}")
            return None

    @staticmethod
    def _normalize_signin_value(value):
        return str(value or "").strip().replace("%25", "%")

    def _signin_credentials(self, account):
        user = self.get_user(account)
        if not user:
            return None

        signin = user.get("signin") or {}
        credentials = {
            key: self._normalize_signin_value(signin.get(key))
            for key in ("kps", "sign", "vcode")
        }

        if not all(credentials.values()):
            cookie = user.get("cookies", "")
            for key in credentials:
                match = re.search(
                    rf"(?<!\w){key}=([a-zA-Z0-9%+/=]+)[;&]?",
                    cookie,
                )
                if match:
                    credentials[key] = self._normalize_signin_value(match.group(1))

        return credentials if all(credentials.values()) else None

    def has_signin_credentials(self, account):
        return self._signin_credentials(account) is not None

    def configure_signin(self, account, enabled=False, **credentials):
        user = self.get_user(account)
        if not user:
            raise ValueError(f"夸克账号 {account} 不存在")

        signin = user.setdefault("signin", {})
        signin["enabled"] = bool(enabled)
        for key in ("kps", "sign", "vcode"):
            value = self._normalize_signin_value(credentials.get(key))
            if value:
                signin[key] = value
            else:
                signin.setdefault(key, "")

        self._save_config()
        return {
            "username": account,
            "signin_enabled": signin["enabled"],
            "signin_configured": self.has_signin_credentials(account),
        }

    def run_enabled_signins(self):
        results = []
        for account, user in self.config.get("quark", {}).get("users", {}).items():
            if (user.get("signin") or {}).get("enabled", False):
                results.append(self.run_signin(account))
        return results

    def _signin_request(self, method, endpoint, credentials, payload=None):
        params = {
            "pr": "ucpro",
            "fr": "android",
            **credentials,
        }
        max_attempts = max(1, min(int(self.config.get("retry", {}).get("max_attempts", 3)), 3))
        last_error = None

        for attempt in range(max_attempts):
            try:
                response = self.session.request(
                    method,
                    f"{self.SIGNIN_BASE_URL}/{endpoint}",
                    params=params,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=30,
                )
                try:
                    body = response.json()
                except ValueError:
                    body = {}

                code = body.get("code")
                message = body.get("message") or body.get("error") or "夸克签到请求失败"
                expired = response.status_code == 401 or str(code) == "50051"
                transient = response.status_code == 429 or response.status_code >= 500

                if expired:
                    raise QuarkSigninError(
                        "签到凭据已过期，请重新抓取 kps、sign、vcode",
                        code=code,
                        http_status=response.status_code,
                        expired=True,
                    )
                if response.status_code >= 400:
                    raise QuarkSigninError(
                        message,
                        code=code,
                        http_status=response.status_code,
                        transient=transient,
                    )

                status = body.get("status")
                if code not in (None, 0) or status not in (None, 0, 200):
                    raise QuarkSigninError(message, code=code)
                if not body.get("data"):
                    raise QuarkSigninError(message, code=code)
                return body["data"]
            except QuarkSigninError as exc:
                last_error = exc
                if not exc.transient or attempt + 1 >= max_attempts:
                    raise
            except requests.RequestException as exc:
                last_error = QuarkSigninError(
                    "夸克签到网络请求失败",
                    transient=True,
                )
                if attempt + 1 >= max_attempts:
                    raise last_error from exc

            time.sleep(min(2 ** attempt, 4) + random.uniform(0, 0.5))

        raise last_error or QuarkSigninError("夸克签到请求失败")

    def get_growth_info(self, account):
        credentials = self._signin_credentials(account)
        if not credentials:
            raise QuarkSigninError("缺少签到凭据 kps、sign、vcode")
        return self._signin_request("GET", "info", credentials)

    def run_signin(self, account):
        if self.provider != "quark":
            return {
                "account": account,
                "success": False,
                "status": "unsupported",
                "message": "签到功能仅支持夸克网盘",
            }

        user = self.get_user(account)
        if not user:
            return {
                "account": account,
                "success": False,
                "status": "not_found",
                "message": "夸克账号不存在",
            }

        result = {
            "account": account,
            "success": False,
            "already_signed": False,
            "reward_bytes": 0,
            "status": "failed",
            "message": "",
        }

        with self._signin_lock:
            try:
                credentials = self._signin_credentials(account)
                if not credentials:
                    raise QuarkSigninError("缺少签到凭据 kps、sign、vcode")

                info = self._signin_request("GET", "info", credentials)
                cap_sign = info.get("cap_sign") or {}
                result.update({
                    "total_capacity": int(info.get("total_capacity") or 0),
                    "sign_reward_total": int((info.get("cap_composition") or {}).get("sign_reward") or 0),
                    "sign_progress": int(cap_sign.get("sign_progress") or 0),
                    "sign_target": int(cap_sign.get("sign_target") or 0),
                })

                if cap_sign.get("sign_daily"):
                    reward = int(cap_sign.get("sign_daily_reward") or 0)
                    result.update({
                        "success": True,
                        "already_signed": True,
                        "reward_bytes": reward,
                        "status": "already_signed",
                        "message": "今日已签到",
                    })
                else:
                    signed = self._signin_request(
                        "POST",
                        "sign",
                        credentials,
                        payload={"sign_cyclic": True},
                    )
                    reward = int(signed.get("sign_daily_reward") or 0)
                    result.update({
                        "success": True,
                        "reward_bytes": reward,
                        "status": "signed",
                        "message": "签到成功",
                        "sign_progress": result["sign_progress"] + 1,
                    })
            except QuarkSigninError as exc:
                result.update({
                    "status": "credentials_expired" if exc.expired else "failed",
                    "message": str(exc),
                    "code": exc.code,
                    "http_status": exc.http_status,
                })
                logger.warning(f"夸克账号 {account} 签到失败: {exc}")
            except Exception as exc:
                result["message"] = "夸克签到发生未知错误"
                logger.exception(f"夸克账号 {account} 签到异常: {exc}")

            previous_meta = user.get("signin_meta") or {}
            user["signin_meta"] = {
                "last_run_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "last_sign_date": (
                    datetime.now().astimezone().date().isoformat()
                    if result["success"]
                    else previous_meta.get("last_sign_date")
                ),
                "last_reward_bytes": result.get("reward_bytes", 0),
                "last_status": result["status"],
                "last_message": result["message"],
            }
            self._save_config()

        return result

    def add_user_from_cookies(self, cookies, username=None):
        try:
            if not cookies or "=" not in cookies:
                raise ValueError("夸克 Cookies 格式无效")

            if not self.validate_cookie(cookies):
                raise ValueError("\u5938\u514b Cookies \u65e0\u6548\u6216\u5df2\u8fc7\u671f")

            username = username or "quark_user"
            users = self.config[self.provider]["users"]
            if username in users:
                index = 1
                while f"{username}_{index}" in users:
                    index += 1
                username = f"{username}_{index}"

            users[username] = {
                "cookies": cookies,
                "name": username,
                "user_id": username,
                "provider": self.provider,
            }

            if not self.config[self.provider].get("current_user"):
                self.config[self.provider]["current_user"] = username

            self._save_config()
            return True
        except Exception as exc:
            logger.error(f"\u6dfb\u52a0 {self.provider} \u7528\u6237\u5931\u8d25: {exc}")
            return False

    def switch_user(self, username):
        if username not in self.config.get(self.provider, {}).get("users", {}):
            return False
        self.config[self.provider]["current_user"] = username
        self._save_config()
        return True

    def remove_user(self, username):
        users = self.config.get(self.provider, {}).get("users", {})
        if username not in users:
            return False

        del users[username]
        if self.config[self.provider].get("current_user") == username:
            self.config[self.provider]["current_user"] = next(iter(users), None)
        self._save_config()
        return True

    def update_user(self, username, cookies):
        if username not in self.config.get(self.provider, {}).get("users", {}):
            return False
        if not self.validate_cookie(cookies):
            return False

        self.config[self.provider]["users"][username]["cookies"] = cookies
        self._save_config()
        return True

    def get_user(self, username):
        return self.config.get(self.provider, {}).get("users", {}).get(username)

    def get_user_cookies(self, username):
        user = self.get_user(username)
        return user.get("cookies", "") if user else ""

    def get_share_folder_name(self, share_url, pwd=None, account=None):
        try:
            cookie, error = self._current_cookie(account)
            if error:
                return {"success": False, "error": error}
            pwd_id = self._extract_pwd_id(share_url)
            passcode = self._extract_passcode(share_url, pwd)
            stoken = self._get_stoken(pwd_id, passcode, cookie)
            items = self._list_share_items(pwd_id, stoken, cookie=cookie)
            if not items:
                return {"success": False, "error": "\u5206\u4eab\u4e2d\u6ca1\u6709\u53ef\u8f6c\u5b58\u7684\u6587\u4ef6"}
            return {"success": True, "folder_name": items[0].get("file_name", pwd_id)}
        except Exception as exc:
            logger.error(f"\u83b7\u53d6\u5938\u514b\u5206\u4eab\u4fe1\u606f\u5931\u8d25: {exc}")
            return {"success": False, "error": str(exc)}

    def _get_stoken(self, pwd_id, passcode="", cookie=None):
        data = self._request(
            "POST",
            f"{self.service['base_url']}/share/sharepage/token",
            headers=self._headers(cookie),
            params=self._params(),
            json={
                "pwd_id": pwd_id,
                "passcode": passcode or "",
                **({"share_for_transfer": True} if self.provider == "uc" else {}),
            },
        )
        stoken = data.get("data", {}).get("stoken")
        if not stoken:
            raise RuntimeError(data.get("message") or "\u83b7\u53d6\u5938\u514b stoken \u5931\u8d25")
        return stoken

    def _list_share_items(self, pwd_id, stoken, pdir_fid="0", cookie=None):
        items = []
        page = 1
        while True:
            data = self._request(
                "GET",
                f"{self.service['base_url']}{self.service['detail_path']}",
                headers=self._headers(cookie),
                params=self._params(
                    {
                        "pwd_id": pwd_id,
                        "passcode": "",
                        "stoken": stoken,
                        "pdir_fid": pdir_fid,
                        "fetch_file_list": "1",
                        "_page": page,
                        "_size": 200,
                        "_fetch_total": 1,
                        "_fetch_task": "1",
                        "_fetch_share": "1",
                    }
                ),
            )
            page_items = data.get("data", {}).get("list", []) or []
            items.extend(page_items)
            if len(page_items) < 200:
                break
            page += 1
        return items

    def _list_drive_items(self, pdir_fid="0", cookie=None):
        items = []
        page = 1
        while True:
            data = self._request(
                "GET",
                f"{self.service['base_url']}/file/sort",
                headers=self._headers(cookie),
                params=self._params(
                    {
                        "pdir_fid": pdir_fid,
                        "_page": page,
                        "_size": 200,
                        "_fetch_total": 1,
                        "_sort": "file_type:asc,updated_at:desc",
                    }
                ),
            )
            page_items = data.get("data", {}).get("list", []) or []
            items.extend(page_items)
            if len(page_items) < 200:
                break
            page += 1
        return items

    def _wait_task(self, task_id, cookie=None):
        if not task_id:
            return None

        for _ in range(30):
            data = self._request(
                "GET",
                f"{self.service['base_url']}/task",
                headers=self._headers(cookie),
                params=self._params({"task_id": task_id, "retry_index": 0}),
            )
            task = data.get("data") or {}
            status = task.get("status")
            if status in (1, 2, 3):
                return task
            time.sleep(1)
        return None

    def _is_dir(self, item):
        return bool(item.get("dir")) or item.get("file_type") == 0

    def _create_folder(self, parent_fid, folder_name, cookie=None):
        data = self._request(
            "POST",
            f"{self.service['base_url']}/file",
            headers=self._headers(cookie),
            params=self._params(),
            json={
                "pdir_fid": parent_fid,
                "file_name": folder_name,
                "dir_init_lock": False,
            },
        )
        payload = data.get("data") or {}
        if payload.get("fid"):
            return payload["fid"]

        task = self._wait_task(payload.get("task_id"), cookie)
        save_as = (task or {}).get("save_as") or {}
        if save_as.get("fid"):
            return save_as["fid"]

        for item in self._list_drive_items(parent_fid, cookie):
            if item.get("file_name") == folder_name and self._is_dir(item):
                return item.get("fid")

        raise RuntimeError(f"\u521b\u5efa\u5938\u514b\u6587\u4ef6\u5939\u5931\u8d25: {folder_name}")

    def _ensure_dir(self, save_dir, cookie=None):
        current_fid = "0"
        parts = [part for part in (save_dir or "/").strip("/").split("/") if part]

        for part in parts:
            found = None
            for item in self._list_drive_items(current_fid, cookie):
                if item.get("file_name") == part and self._is_dir(item):
                    found = item.get("fid")
                    break
            current_fid = found or self._create_folder(current_fid, part, cookie)

        return current_fid

    def _ensure_subdir(self, parent_fid, rel_dir, cookie=None):
        current_fid = parent_fid
        parts = [part for part in (rel_dir or "").strip("/").split("/") if part]
        for part in parts:
            found = None
            for item in self._list_drive_items(current_fid, cookie):
                if item.get("file_name") == part and self._is_dir(item):
                    found = item.get("fid")
                    break
            current_fid = found or self._create_folder(current_fid, part, cookie)
        return current_fid

    def _flatten_share_files(self, pwd_id, stoken, cookie=None, share_cache=None):
        files = []
        queue = [("0", "")]
        while queue:
            pdir_fid, prefix = queue.pop(0)
            cache_key = (pwd_id, pdir_fid)
            if share_cache is not None and cache_key in share_cache:
                items = share_cache[cache_key]
            else:
                items = self._list_share_items(pwd_id, stoken, pdir_fid=pdir_fid, cookie=cookie)
                if share_cache is not None:
                    share_cache[cache_key] = items
            for item in items:
                name = item.get("file_name") or item.get("title") or item.get("fid")
                rel_path = posixpath.join(prefix, name) if prefix else name
                if self._is_dir(item):
                    queue.append((item.get("fid"), rel_path))
                else:
                    files.append((item, rel_path))
        return files

    def _existing_names(self, parent_fid, existing_cache, cookie=None):
        if parent_fid not in existing_cache:
            existing_cache[parent_fid] = {
                item.get("file_name")
                for item in self._list_drive_items(parent_fid, cookie)
                if item.get("file_name")
            }
        return existing_cache[parent_fid]

    def _save_files(self, fid_list, token_list, to_pdir_fid, pwd_id, stoken, cookie=None):
        data = self._request(
            "POST",
            self.service["save_url"],
            headers=self._headers(cookie),
            params=self._params(),
            json={
                "fid_list": fid_list,
                "fid_token_list": token_list,
                "to_pdir_fid": to_pdir_fid,
                "pwd_id": pwd_id,
                "stoken": stoken,
                "pdir_fid": "0",
                "scene": "link",
            },
        )
        self._wait_task(data.get("data", {}).get("task_id"), cookie)

    def _apply_regex_rules(self, file_name, task_config):
        pattern = (task_config or {}).get("regex_pattern") or ""
        replace = (task_config or {}).get("regex_replace") or ""
        if not pattern:
            return True, file_name

        if not re.search(pattern, file_name):
            return False, file_name
        if replace:
            return True, re.sub(pattern, replace, file_name)
        return True, file_name

    def transfer_share(
        self,
        share_url,
        pwd=None,
        new_files=None,
        save_dir=None,
        progress_callback=None,
        task_config=None,
    ):
        try:
            account = (task_config or {}).get("account")
            cookie, error = self._current_cookie(account)
            if error:
                return {"success": False, "error": error}
            label = self.service["label"]

            if progress_callback:
                progress_callback("info", f"[{label} 1/4] \u89e3\u6790\u5206\u4eab\u94fe\u63a5")

            pwd_id = self._extract_pwd_id(share_url)
            passcode = self._extract_passcode(share_url, pwd)
            stoken = self._get_stoken(pwd_id, passcode, cookie)

            if progress_callback:
                progress_callback("info", f"[{label} 2/4] \u83b7\u53d6\u5206\u4eab\u6587\u4ef6\u5217\u8868")

            share_cache = {}
            existing_cache = {}
            share_files = self._flatten_share_files(pwd_id, stoken, cookie, share_cache)
            if not share_files:
                return {"success": False, "error": "\u5206\u4eab\u4e2d\u6ca1\u6709\u53ef\u8f6c\u5b58\u7684\u6587\u4ef6"}

            if progress_callback:
                progress_callback("info", f"[{label} 3/4] \u51c6\u5907\u4fdd\u5b58\u76ee\u5f55")

            target_parent = self._ensure_dir(save_dir or "/", cookie)

            candidates = []
            skipped = 0
            rel_dirs = set()
            for item, rel_path in share_files:
                should_transfer, final_path = self._apply_regex_rules(rel_path, task_config)
                if not should_transfer:
                    skipped += 1
                    continue
                rel_dir = posixpath.dirname(final_path)
                if rel_dir and rel_dir not in (".", ""):
                    rel_dirs.add(rel_dir)
                candidates.append((item, final_path, rel_dir))

            parent_by_rel_dir = {"": target_parent}
            for rel_dir in sorted(rel_dirs, key=lambda path: path.count("/")):
                parent_by_rel_dir[rel_dir] = self._ensure_subdir(
                    target_parent, rel_dir, cookie
                )

            items_to_save = []
            for item, final_path, rel_dir in candidates:
                file_name = posixpath.basename(final_path)
                copy_parent = parent_by_rel_dir.get(rel_dir or "", target_parent)
                if file_name in self._existing_names(copy_parent, existing_cache, cookie):
                    skipped += 1
                    if progress_callback:
                        skip_path = posixpath.join(save_dir or "/", final_path).replace("\\", "/")
                        progress_callback("info", f"\u6587\u4ef6\u5df2\u5b58\u5728\uff0c\u8df3\u8fc7: {skip_path}")
                    continue
                fid = item.get("fid")
                token = item.get("share_fid_token")
                if fid and token:
                    items_to_save.append((fid, token, copy_parent, final_path, file_name))

            if not items_to_save:
                return {
                    "success": True,
                    "message": "\u6ca1\u6709\u65b0\u6587\u4ef6\u9700\u8981\u8f6c\u5b58",
                    "skipped": True,
                    "transferred_files": [],
                    "skipped_count": skipped,
                }

            if progress_callback:
                progress_callback("info", f"[{label} 4/4] \u8f6c\u5b58 {len(items_to_save)} \u4e2a\u6587\u4ef6")

            transferred_files = []
            batch_size = 100
            by_parent = {}
            for fid, token, copy_parent, final_path, file_name in items_to_save:
                by_parent.setdefault(copy_parent, []).append((fid, token, final_path, file_name))

            for copy_parent, parent_items in by_parent.items():
                for offset in range(0, len(parent_items), batch_size):
                    batch = parent_items[offset : offset + batch_size]
                    self._save_files(
                        [item[0] for item in batch],
                        [item[1] for item in batch],
                        copy_parent,
                        pwd_id,
                        stoken,
                        cookie,
                    )
                    for _, _, final_path, file_name in batch:
                        existing_cache.setdefault(copy_parent, set()).add(file_name)
                        transferred_files.append(
                            posixpath.join(save_dir or "/", final_path).replace("\\", "/")
                        )
                        if progress_callback:
                            progress_callback(
                                "info",
                                f"\u6dfb\u52a0\u6587\u4ef6\uff1a{transferred_files[-1]}",
                            )

            if progress_callback:
                progress_callback("info", f"[{label} 4/4] \u8f6c\u5b58\u5b8c\u6210")

            return {
                "success": True,
                "message": f"{label}\u8f6c\u5b58\u6210\u529f",
                "skipped": False,
                "transferred_files": transferred_files,
                "skipped_count": skipped,
            }
        except Exception as exc:
            logger.error(f"{self.service['label']}\u8f6c\u5b58\u5931\u8d25: {exc}")
            return {"success": False, "error": str(exc)}

    def is_valid(self):
        cookie, error = self._current_cookie()
        if error:
            return False
        return self.validate_cookie(cookie)
