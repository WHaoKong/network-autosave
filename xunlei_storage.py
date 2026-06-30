import hashlib
import json
import posixpath
import random
import re
import time
import base64
from threading import Lock
from urllib.parse import parse_qs, urlparse

import requests
from loguru import logger


WEB_ALGORITHMS = (
    "b9Dldv6kRsRyOG4tFHzeJ4RbOi0n7nO8omFouLVgvLNB.TEHDOteMPrRB66yQIF9tF+pfPAIesa/xg."
    "Fmx27GlNbrIxiPSQVm.crlPVriPRAiuCEKZvK4yihP55gTRvLd7qDVLsDtWzhkXt5Iqs7TpoP."
    "E2toogseEdgXmlfnz1ppUhUvD9B2jgSA+YG.a2f3L0AioU+0PvTeCtk.6d6w1xX9j95GEPNpd+T4HmbTceZNEF310ppRe."
    "BvsJ+CSS7i.Rv"
).split(".")
WEB_CLIENT_VERSION = "1.82.0"
WEB_PACKAGE_NAME = "pan.xunlei.com"
FOLDER_KIND = "drive#folder"
FILE_KIND = "drive#file"
FILE_FILTERS = json.dumps({"phase": {"eq": "PHASE_TYPE_COMPLETE"}, "trashed": {"eq": False}})


class XunleiStorage:
    API_BASE = "https://api-pan.xunlei.com/drive/v1"
    CAPTCHA_URL = "https://xluser-ssl.xunlei.com/v1/shield/captcha/init"
    REQUEST_INTERVAL = 0.25
    CAPTCHA_MIN_INTERVAL = 2.0
    CAPTCHA_TTL = 300
    MAX_429_RETRIES = 5
    MAX_CAPTCHA_RETRIES = 2

    def __init__(self, config, save_config_callback=None):
        self.config = config
        self._save_config_callback = save_config_callback
        self.session = requests.Session()
        self._last_request_time = 0.0
        self._captcha_cache = {}
        self._captcha_last_init = 0.0
        self._captcha_lock = Lock()
        self._ensure_config()

    def _ensure_config(self):
        xunlei = self.config.setdefault("xunlei", {})
        xunlei.setdefault("users", {})
        xunlei.setdefault("current_user", None)

    def _save_config(self):
        if self._save_config_callback:
            self._save_config_callback()

    def _throttle(self):
        elapsed = time.time() - self._last_request_time
        if elapsed < self.REQUEST_INTERVAL:
            time.sleep(self.REQUEST_INTERVAL - elapsed)

    def _parse_token(self, account=None):
        current_user = account or self.config.get("xunlei", {}).get("current_user")
        if not current_user:
            return None, None, None, "\u672a\u8bbe\u7f6e\u8fc5\u96f7\u7f51\u76d8\u7528\u6237"

        user_info = self.config.get("xunlei", {}).get("users", {}).get(current_user) or {}
        token = (user_info.get("cookies") or "").strip()
        if not token:
            return None, None, None, f"\u8fc5\u96f7\u7f51\u76d8\u7528\u6237 {current_user} \u672a\u914d\u7f6e Authorization"
        if not token.lower().startswith("bearer "):
            token = f"Bearer {token}"

        try:
            payload = json.loads(base64.urlsafe_b64decode(token.split(" ", 1)[1].split(".")[1] + "=="))
        except Exception as exc:
            return None, None, None, f"\u65e0\u6548\u7684\u8fc5\u96f7 Authorization: {exc}"

        client_id = payload.get("aud") or "Xqp0kJBXWhwaTpB6"
        user_id = payload.get("sub") or current_user
        device_id = user_info.get("device_id") or hashlib.md5(f"pan-web-{user_id}".encode()).hexdigest()
        return token, {"client_id": client_id, "user_id": user_id, "device_id": device_id}, current_user, None

    def _md5(self, value):
        return hashlib.md5(value.encode()).hexdigest()

    def _captcha_sign(self, auth_ctx):
        timestamp = str(int(time.time() * 1000))
        source = (
            auth_ctx["client_id"]
            + WEB_CLIENT_VERSION
            + WEB_PACKAGE_NAME
            + auth_ctx["device_id"]
            + timestamp
        )
        for algorithm in WEB_ALGORITHMS:
            source = self._md5(source + algorithm)
        return timestamp, f"1.{source}"

    def _init_captcha(self, auth_ctx, action):
        timestamp, sign = self._captcha_sign(auth_ctx)
        body = {
            "action": action,
            "captcha_token": "",
            "client_id": auth_ctx["client_id"],
            "device_id": auth_ctx["device_id"],
            "redirect_uri": "xlaccsdk01://xunlei.com/callback?state=harbor",
            "meta": {
                "client_version": WEB_CLIENT_VERSION,
                "package_name": WEB_PACKAGE_NAME,
                "user_id": auth_ctx["user_id"],
                "timestamp": timestamp,
                "captcha_sign": sign,
            },
        }
        response = self.session.post(self.CAPTCHA_URL, json=body, timeout=30)
        data = {}
        if response.content:
            try:
                data = response.json()
            except ValueError:
                data = {}
        if response.status_code >= 400:
            message = data.get("error_description") or data.get("error") or response.text[:200]
            if response.status_code == 409 or "too frequent" in (message or "").lower():
                raise RuntimeError("\u8fc5\u96f7\u63a5\u53e3\u8bf7\u6c42\u8fc7\u4e8e\u9891\u7e41\uff0c\u8bf7\u7a0d\u540e\u518d\u8bd5")
            raise RuntimeError(message or f"captcha init failed: HTTP {response.status_code}")
        token = data.get("captcha_token")
        if not token:
            raise RuntimeError(data.get("error_description") or data.get("message") or "\u83b7\u53d6 captcha_token \u5931\u8d25")
        return token

    def _invalidate_captcha_cache(self, auth_ctx):
        user_id = auth_ctx.get("user_id")
        self._captcha_cache = {
            key: value for key, value in self._captcha_cache.items() if key[0] != user_id
        }

    def _get_captcha_token(self, auth_ctx, action):
        user_id = auth_ctx["user_id"]
        now = time.time()
        cached = self._captcha_cache.get((user_id, action))
        if cached and cached[1] > now:
            return cached[0]
        for (cached_user, _), (token, expire_at) in self._captcha_cache.items():
            if cached_user == user_id and expire_at > now:
                return token

        with self._captcha_lock:
            cached = self._captcha_cache.get((user_id, action))
            if cached and cached[1] > time.time():
                return cached[0]

            last_error = None
            for attempt in range(self.MAX_CAPTCHA_RETRIES):
                elapsed = time.time() - self._captcha_last_init
                if elapsed < self.CAPTCHA_MIN_INTERVAL:
                    time.sleep(self.CAPTCHA_MIN_INTERVAL - elapsed)
                try:
                    token = self._init_captcha(auth_ctx, action)
                    self._captcha_last_init = time.time()
                    expire_at = time.time() + self.CAPTCHA_TTL
                    self._captcha_cache[(user_id, action)] = (token, expire_at)
                    return token
                except Exception as exc:
                    last_error = exc
                    if attempt >= self.MAX_CAPTCHA_RETRIES - 1:
                        break
                    delay = 60.0 if "\u9891\u7e41" in str(exc) or "too frequent" in str(exc).lower() else 3.0
                    logger.warning(f"\u8fc5\u96f7 captcha \u521d\u59cb\u5316\u5931\u8d25\uff0c{delay:.0f}s \u540e\u91cd\u8bd5: {exc}")
                    time.sleep(delay)
            raise RuntimeError(str(last_error) if last_error else "\u83b7\u53d6 captcha_token \u5931\u8d25")

    def _ensure_session_captcha(self, auth_ctx, action):
        if not action:
            raise ValueError("xunlei captcha action is required")
        session_map = auth_ctx.setdefault("_session_captcha_map", {})
        if action in session_map:
            return session_map[action]
        token = self._get_captcha_token(auth_ctx, action)
        session_map[action] = token
        return token

    def _refresh_session_captcha(self, auth_ctx, action):
        if action:
            auth_ctx.get("_session_captcha_map", {}).pop(action, None)
        else:
            auth_ctx.pop("_session_captcha_map", None)
        self._invalidate_captcha_cache(auth_ctx)
        return self._ensure_session_captcha(auth_ctx, action)

    def _headers(self, token, auth_ctx, action):
        return {
            "Authorization": token,
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Origin": "https://pan.xunlei.com",
            "Referer": "https://pan.xunlei.com/",
            "X-Device-Id": auth_ctx["device_id"],
            "X-Client-Id": auth_ctx["client_id"],
            "X-Client-Version": WEB_CLIENT_VERSION,
            "X-Captcha-Token": self._ensure_session_captcha(auth_ctx, action),
        }

    def _request(self, method, path, token, auth_ctx, action, **kwargs):
        url = path if path.startswith("http") else f"{self.API_BASE}{path}"
        last_error = None
        for attempt in range(self.MAX_429_RETRIES + 1):
            self._throttle()
            response = self.session.request(
                method,
                url,
                timeout=30,
                headers=self._headers(token, auth_ctx, action),
                **kwargs,
            )
            self._last_request_time = time.time()
            if response.status_code == 429:
                last_error = requests.HTTPError(
                    f"429 Client Error: Too Many Requests for url: {url}",
                    response=response,
                )
                if attempt >= self.MAX_429_RETRIES:
                    response.raise_for_status()
                delay = min(8.0, 1.5 * (attempt + 1)) + random.uniform(0.2, 0.8)
                logger.warning(f"\u8fc5\u96f7\u7f51\u76d8 API \u9650\u6d41\uff0c{delay:.1f}s \u540e\u91cd\u8bd5")
                time.sleep(delay)
                continue

            data = {}
            if response.content:
                try:
                    data = response.json()
                except ValueError:
                    response.raise_for_status()
                    raise RuntimeError(response.text[:200])

            if response.status_code >= 400 or data.get("error"):
                message = data.get("error_description") or data.get("error") or response.text[:200]
                if data.get("error_code") == 9 and attempt < self.MAX_429_RETRIES:
                    self._refresh_session_captcha(auth_ctx, action)
                    time.sleep(1.0)
                    continue
                raise RuntimeError(message)

            return data

        if last_error:
            raise last_error
        raise RuntimeError(f"\u8fc5\u96f7\u7f51\u76d8\u8bf7\u6c42\u5931\u8d25: {url}")

    def _extract_share_id(self, share_url):
        parsed = urlparse(share_url.split("#")[0])
        match = re.search(r"/s/([A-Za-z0-9_-]+)", parsed.path)
        if match:
            return match.group(1)
        params = parse_qs(parsed.query)
        if params.get("share_id"):
            return params["share_id"][0]
        raise ValueError("\u65e0\u6cd5\u89e3\u6790\u8fc5\u96f7\u5206\u4eab ID")

    def _extract_passcode(self, share_url, pwd=None):
        if pwd:
            return pwd
        parsed = urlparse(share_url.split("#")[0])
        params = parse_qs(parsed.query)
        for key in ("pwd", "pass_code", "password"):
            if params.get(key):
                return params[key][0]
        fragment = share_url.split("#", 1)
        if len(fragment) > 1 and fragment[1]:
            return fragment[1]
        return ""

    def _share_status_error(self, status, status_text=""):
        if status in ("", "OK", "NORMAL"):
            return None
        if status == "SENSITIVE_RESOURCE":
            return "\u5206\u4eab\u5185\u5bb9\u88ab\u8fc5\u96f7\u6807\u8bb0\u4e3a\u654f\u611f\u8d44\u6e90\uff0c\u65e0\u6cd5\u8f6c\u5b58"
        if status == "PASS_CODE_EMPTY":
            return "\u5206\u4eab\u94fe\u63a5\u9700\u8981\u63d0\u53d6\u7801"
        if status == "PASS_CODE_ERROR":
            return "\u5206\u4eab\u63d0\u53d6\u7801\u9519\u8bef"
        if status == "EXPIRED":
            return "\u5206\u4eab\u94fe\u63a5\u5df2\u8fc7\u671f"
        return status_text or f"\u5206\u4eab\u72b6\u6001\u5f02\u5e38: {status}"

    def _list_share_page(self, token, auth_ctx, share_id, pass_code, pass_code_token="", parent_id="", page_token=""):
        params = {
            "share_id": share_id,
            "pass_code": pass_code,
            "limit": "100",
            "page_token": page_token,
            "thumbnail_size": "SIZE_SMALL",
        }
        if pass_code_token:
            params["pass_code_token"] = pass_code_token
        if parent_id:
            params["parent_id"] = parent_id
        return self._request(
            "GET",
            "/share",
            token,
            auth_ctx,
            "GET:/drive/v1/share",
            params=params,
        )

    def _flatten_share_files(self, token, auth_ctx, share_id, pass_code):
        queue = [("", "")]
        pass_code_token = ""
        title = ""
        files = []

        while queue:
            parent_id, prefix = queue.pop(0)
            page_token = ""
            while True:
                data = self._list_share_page(
                    token,
                    auth_ctx,
                    share_id,
                    pass_code,
                    pass_code_token=pass_code_token,
                    parent_id=parent_id,
                    page_token=page_token,
                )
                if not pass_code_token:
                    pass_code_token = data.get("pass_code_token") or pass_code_token
                if not title:
                    title = data.get("title") or title
                if parent_id == "" and not prefix:
                    error = self._share_status_error(data.get("share_status"), data.get("share_status_text"))
                    if error:
                        raise RuntimeError(error)

                for item in data.get("files") or []:
                    name = item.get("name") or item.get("id")
                    rel_path = posixpath.join(prefix, name) if prefix else name
                    if item.get("kind") == FOLDER_KIND:
                        queue.append((item.get("id"), rel_path))
                    else:
                        files.append((item, rel_path, pass_code_token))

                page_token = data.get("next_page_token") or ""
                if not page_token:
                    break

        return files, pass_code_token, title

    def _list_drive_page(self, token, auth_ctx, parent_id="", page_token="", drive_cache=None):
        cache_key = (parent_id, page_token)
        if drive_cache is not None and cache_key in drive_cache:
            return drive_cache[cache_key]

        data = self._request(
            "GET",
            "/files",
            token,
            auth_ctx,
            "GET:/drive/v1/files",
            params={
                "parent_id": parent_id,
                "filters": FILE_FILTERS,
                "limit": "100",
                "page_token": page_token,
            },
        )
        if drive_cache is not None:
            drive_cache[cache_key] = data
        return data

    def _list_drive_items(self, token, auth_ctx, parent_id="", drive_cache=None):
        items = []
        page_token = ""
        while True:
            data = self._list_drive_page(token, auth_ctx, parent_id, page_token, drive_cache)
            items.extend(data.get("files") or [])
            page_token = data.get("next_page_token") or ""
            if not page_token:
                return items

    def _ensure_dir(self, token, auth_ctx, save_dir, drive_cache=None):
        current = ""
        parts = [part for part in (save_dir or "/").strip("/").split("/") if part]
        for part in parts:
            found = next(
                (
                    item
                    for item in self._list_drive_items(token, auth_ctx, current, drive_cache)
                    if item.get("name") == part and item.get("kind") == FOLDER_KIND
                ),
                None,
            )
            if found:
                current = found.get("id") or current
                continue
            data = self._request(
                "POST",
                "/files",
                token,
                auth_ctx,
                "POST:/drive/v1/files",
                json={"kind": FOLDER_KIND, "name": part, "parent_id": current},
            )
            current = data.get("id") or (data.get("file") or {}).get("id")
            if not current:
                raise RuntimeError(f"\u521b\u5efa\u8fc5\u96f7\u76ee\u5f55\u5931\u8d25: {part}")
            if drive_cache is not None:
                drive_cache.clear()
        return current

    def _ensure_subdir(self, token, auth_ctx, parent_id, rel_dir, drive_cache=None):
        current = parent_id
        parts = [part for part in (rel_dir or "").strip("/").split("/") if part]
        for part in parts:
            found = next(
                (
                    item
                    for item in self._list_drive_items(token, auth_ctx, current, drive_cache)
                    if item.get("name") == part and item.get("kind") == FOLDER_KIND
                ),
                None,
            )
            if found:
                current = found.get("id")
                continue
            data = self._request(
                "POST",
                "/files",
                token,
                auth_ctx,
                "POST:/drive/v1/files",
                json={"kind": FOLDER_KIND, "name": part, "parent_id": current},
            )
            current = data.get("id") or (data.get("file") or {}).get("id")
            if not current:
                raise RuntimeError(f"\u521b\u5efa\u8fc5\u96f7\u76ee\u5f55\u5931\u8d25: {part}")
            if drive_cache is not None:
                drive_cache.clear()
        return current

    def _existing_names(self, token, auth_ctx, parent_id, existing_cache, drive_cache=None):
        if parent_id not in existing_cache:
            existing_cache[parent_id] = {
                item.get("name")
                for item in self._list_drive_items(token, auth_ctx, parent_id, drive_cache)
                if item.get("name")
            }
        return existing_cache[parent_id]

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

    def _wait_restore_task(self, token, auth_ctx, task_id):
        if not task_id:
            return
        for _ in range(60):
            data = self._request(
                "GET",
                f"/tasks/{task_id}",
                token,
                auth_ctx,
                "GET:/drive/v1/tasks/{task_id}",
            )
            phase = (data.get("phase") or data.get("status") or "").upper()
            if phase in ("PHASE_TYPE_COMPLETE", "SUCCESS", "COMPLETED", "DONE"):
                return
            if phase in ("PHASE_TYPE_ERROR", "FAILED", "ERROR"):
                raise RuntimeError(data.get("message") or "\u8fc5\u96f7\u8f6c\u5b58\u4efb\u52a1\u5931\u8d25")
            time.sleep(1)

    def _restore_file(self, token, auth_ctx, share_id, pass_code, pass_code_token, file_id, parent_id):
        data = self._request(
            "POST",
            "/share/restore",
            token,
            auth_ctx,
            "POST:/drive/v1/share/restore",
            json={
                "share_id": share_id,
                "pass_code": pass_code,
                "pass_code_token": pass_code_token,
                "file_ids": [file_id],
                "parent_id": parent_id,
                "ancestor_ids": [],
            },
        )
        error = self._share_status_error(data.get("share_status"), data.get("share_status_text"))
        if error:
            raise RuntimeError(error)
        restore_status = (data.get("restore_status") or "").upper()
        if restore_status in ("FAILED", "ERROR"):
            raise RuntimeError(data.get("restore_status_text") or "\u8fc5\u96f7\u8f6c\u5b58\u5931\u8d25")
        self._wait_restore_task(token, auth_ctx, data.get("restore_task_id"))

    def get_quota(self, account=None):
        token, auth_ctx, _, error = self._parse_token(account)
        if error:
            return None
        try:
            data = self._request(
                "GET",
                "/about",
                token,
                auth_ctx,
                "GET:/drive/v1/about",
            )
            quota = data.get("quota") or {}
            return {
                "total": int(quota.get("limit") or 0),
                "used": int(quota.get("usage") or 0),
            }
        except Exception as exc:
            logger.warning(f"\u8fc5\u96f7 quota fetch failed: {exc}")
            return None

    def get_share_folder_name(self, share_url, pwd=None, account=None):
        try:
            token, auth_ctx, _, error = self._parse_token(account)
            if error:
                return {"success": False, "error": error}
            share_id = self._extract_share_id(share_url)
            pass_code = self._extract_passcode(share_url, pwd)
            _, _, title = self._flatten_share_files(token, auth_ctx, share_id, pass_code)
            if title:
                return {"success": True, "folder_name": title}
            return {"success": True, "folder_name": share_id}
        except Exception as exc:
            logger.error(f"\u83b7\u53d6\u8fc5\u96f7\u5206\u4eab\u4fe1\u606f\u5931\u8d25: {exc}")
            return {"success": False, "error": str(exc)}

    def transfer_share(self, share_url, pwd=None, new_files=None, save_dir=None, progress_callback=None, task_config=None):
        try:
            account = (task_config or {}).get("account")
            token, auth_ctx, _, error = self._parse_token(account)
            if error:
                return {"success": False, "error": error}

            if progress_callback:
                progress_callback("info", "[\u8fc5\u96f7\u7f51\u76d8 1/4] \u89e3\u6790\u5206\u4eab\u94fe\u63a5")
            share_id = self._extract_share_id(share_url)
            pass_code = self._extract_passcode(share_url, pwd)

            if progress_callback:
                progress_callback("info", "[\u8fc5\u96f7\u7f51\u76d8 2/4] \u83b7\u53d6\u5206\u4eab\u6587\u4ef6\u5217\u8868")
            share_files, pass_code_token, _ = self._flatten_share_files(token, auth_ctx, share_id, pass_code)
            if not share_files:
                return {"success": False, "error": "\u5206\u4eab\u4e2d\u6ca1\u6709\u53ef\u8f6c\u5b58\u7684\u6587\u4ef6"}

            if progress_callback:
                progress_callback("info", "[\u8fc5\u96f7\u7f51\u76d8 3/4] \u51c6\u5907\u4fdd\u5b58\u76ee\u5f55")
            drive_cache = {}
            existing_cache = {}
            target_parent = self._ensure_dir(token, auth_ctx, save_dir or "/", drive_cache)

            candidates = []
            skipped = 0
            rel_dirs = set()
            for item, rel_path, item_pass_code_token in share_files:
                should_transfer, final_path = self._apply_regex_rules(rel_path, task_config)
                if not should_transfer:
                    skipped += 1
                    continue
                rel_dir = posixpath.dirname(final_path)
                if rel_dir and rel_dir not in (".", ""):
                    rel_dirs.add(rel_dir)
                candidates.append((item, final_path, rel_dir, item_pass_code_token or pass_code_token))

            parent_by_rel_dir = {"": target_parent}
            for rel_dir in sorted(rel_dirs, key=lambda path: path.count("/")):
                parent_by_rel_dir[rel_dir] = self._ensure_subdir(
                    token, auth_ctx, target_parent, rel_dir, drive_cache
                )

            items_to_copy = []
            for item, final_path, rel_dir, item_pass_code_token in candidates:
                file_name = posixpath.basename(final_path)
                copy_parent = parent_by_rel_dir.get(rel_dir or "", target_parent)
                if file_name in self._existing_names(token, auth_ctx, copy_parent, existing_cache, drive_cache):
                    skipped += 1
                    if progress_callback:
                        skip_path = posixpath.join(save_dir or "/", final_path).replace("\\", "/")
                        progress_callback("info", f"\u6587\u4ef6\u5df2\u5b58\u5728\uff0c\u8df3\u8fc7: {skip_path}")
                    continue
                items_to_copy.append((item, copy_parent, final_path, file_name, item_pass_code_token))

            if not items_to_copy:
                return {
                    "success": True,
                    "message": "\u6ca1\u6709\u65b0\u6587\u4ef6\u9700\u8981\u8f6c\u5b58",
                    "skipped": True,
                    "transferred_files": [],
                    "skipped_count": skipped,
                }

            if progress_callback:
                progress_callback("info", f"[\u8fc5\u96f7\u7f51\u76d8 4/4] \u8f6c\u5b58 {len(items_to_copy)} \u4e2a\u6587\u4ef6")
            transferred_files = []
            for item, copy_parent, final_path, file_name, item_pass_code_token in items_to_copy:
                file_id = item.get("id")
                if not file_id:
                    continue
                self._restore_file(
                    token,
                    auth_ctx,
                    share_id,
                    pass_code,
                    item_pass_code_token,
                    file_id,
                    copy_parent,
                )
                existing_cache.setdefault(copy_parent, set()).add(file_name)
                transferred_files.append(posixpath.join(save_dir or "/", final_path).replace("\\", "/"))
                if progress_callback:
                    progress_callback("info", f"\u6dfb\u52a0\u6587\u4ef6\uff1a{transferred_files[-1]}")

            return {
                "success": True,
                "message": "\u8fc5\u96f7\u7f51\u76d8\u8f6c\u5b58\u6210\u529f",
                "skipped": False,
                "transferred_files": transferred_files,
                "skipped_count": skipped,
            }
        except Exception as exc:
            logger.error(f"\u8fc5\u96f7\u7f51\u76d8\u8f6c\u5b58\u5931\u8d25: {exc}")
            return {"success": False, "error": str(exc)}
