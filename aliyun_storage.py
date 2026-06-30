import posixpath
import random
import re
import time
from urllib.parse import parse_qs, urlparse

import requests
from loguru import logger


class AliyunStorage:
    API_BASE = "https://api.aliyundrive.com"
    REQUEST_INTERVAL = 0.35
    MAX_429_RETRIES = 5

    def __init__(self, config, save_config_callback=None):
        self.config = config
        self._save_config_callback = save_config_callback
        self.session = requests.Session()
        self._last_request_time = 0.0
        self._ensure_config()

    def _ensure_config(self):
        aliyun = self.config.setdefault("aliyun", {})
        aliyun.setdefault("users", {})
        aliyun.setdefault("current_user", None)

    def _save_config(self):
        if self._save_config_callback:
            self._save_config_callback()

    def _throttle(self):
        elapsed = time.time() - self._last_request_time
        if elapsed < self.REQUEST_INTERVAL:
            time.sleep(self.REQUEST_INTERVAL - elapsed)

    def _current_token(self, account=None):
        current_user = account or self.config.get("aliyun", {}).get("current_user")
        if not current_user:
            return None, "\u672a\u8bbe\u7f6e\u963f\u91cc\u4e91\u76d8\u7528\u6237"

        user_info = self.config.get("aliyun", {}).get("users", {}).get(current_user)
        token = (user_info or {}).get("cookies") or ""
        if not token:
            return None, f"\u963f\u91cc\u4e91\u76d8\u7528\u6237 {current_user} \u672a\u914d\u7f6e Authorization"
        if not token.lower().startswith("bearer "):
            token = f"Bearer {token}"
        return token, None

    def _headers(self, token=None, share_token=None):
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Origin": "https://www.alipan.com",
            "Referer": "https://www.alipan.com/",
        }
        if token:
            headers["Authorization"] = token
        if share_token:
            headers["x-share-token"] = share_token
        return headers

    def _request(self, method, path_or_url, **kwargs):
        url = path_or_url if path_or_url.startswith("http") else f"{self.API_BASE}{path_or_url}"
        last_error = None
        for attempt in range(self.MAX_429_RETRIES + 1):
            self._throttle()
            response = self.session.request(method, url, timeout=30, **kwargs)
            self._last_request_time = time.time()
            if response.status_code == 429:
                last_error = requests.HTTPError(
                    f"429 Client Error: Too Many Requests for url: {url}",
                    response=response,
                )
                if attempt >= self.MAX_429_RETRIES:
                    response.raise_for_status()
                delay = min(8.0, 1.5 * (attempt + 1)) + random.uniform(0.2, 0.8)
                logger.warning(f"\u963f\u91cc\u4e91\u76d8 API \u9650\u6d41\uff0c{delay:.1f}s \u540e\u91cd\u8bd5 ({attempt + 1}/{self.MAX_429_RETRIES})")
                time.sleep(delay)
                continue
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict) and data.get("code") and not data.get("items"):
                raise RuntimeError(data.get("message") or data.get("code") or data)
            return data
        if last_error:
            raise last_error
        raise RuntimeError(f"\u963f\u91cc\u4e91\u76d8\u8bf7\u6c42\u5931\u8d25: {url}")

    def _extract_share_id(self, share_url):
        parsed = urlparse(share_url.split("#")[0])
        match = re.search(r"/s/([A-Za-z0-9_-]+)", parsed.path)
        if match:
            return match.group(1)
        params = parse_qs(parsed.query)
        if params.get("share_id"):
            return params["share_id"][0]
        raise ValueError("\u65e0\u6cd5\u89e3\u6790\u963f\u91cc\u4e91\u76d8\u5206\u4eab ID")

    def _extract_passcode(self, share_url, pwd=None):
        if pwd:
            return pwd
        parsed = urlparse(share_url.split("#")[0])
        params = parse_qs(parsed.query)
        for key in ("pwd", "share_pwd", "password"):
            if params.get(key):
                return params[key][0]
        return ""

    def _get_share_token(self, share_id, share_pwd=""):
        data = self._request(
            "POST",
            "/v2/share_link/get_share_token",
            headers=self._headers(),
            json={"share_id": share_id, "share_pwd": share_pwd or ""},
        )
        token = data.get("share_token")
        if not token:
            raise RuntimeError(data.get("message") or "\u83b7\u53d6\u963f\u91cc\u4e91\u76d8 share_token \u5931\u8d25")
        return token

    def _get_drive_id(self, token):
        data = self._request(
            "POST",
            "/v2/user/get",
            headers=self._headers(token),
            json={},
        )
        drive_id = data.get("default_drive_id") or data.get("resource_drive_id") or data.get("backup_drive_id")
        if not drive_id:
            raise RuntimeError("\u65e0\u6cd5\u83b7\u53d6\u963f\u91cc\u4e91\u76d8 drive_id")
        return drive_id

    def _list_share_items(self, share_id, share_token, parent_file_id="root", share_cache=None):
        cache_key = (share_id, parent_file_id)
        if share_cache is not None and cache_key in share_cache:
            return share_cache[cache_key]

        items = []
        marker = ""
        while True:
            payload = {
                "share_id": share_id,
                "parent_file_id": parent_file_id,
                "limit": 100,
                "order_by": "name",
                "order_direction": "ASC",
            }
            if marker:
                payload["marker"] = marker
            data = self._request(
                "POST",
                "/adrive/v2/file/list_by_share",
                headers=self._headers(share_token=share_token),
                json=payload,
            )
            items.extend(data.get("items", []) or [])
            marker = data.get("next_marker") or ""
            if not marker:
                break

        if share_cache is not None:
            share_cache[cache_key] = items
        return items

    def _list_drive_items(self, token, drive_id, parent_file_id="root", drive_cache=None):
        cache_key = (drive_id, parent_file_id)
        if drive_cache is not None and cache_key in drive_cache:
            return drive_cache[cache_key]

        items = []
        marker = ""
        while True:
            payload = {
                "drive_id": drive_id,
                "parent_file_id": parent_file_id,
                "limit": 100,
                "order_by": "name",
                "order_direction": "ASC",
            }
            if marker:
                payload["marker"] = marker
            data = self._request(
                "POST",
                "/adrive/v3/file/list",
                headers=self._headers(token),
                json=payload,
            )
            items.extend(data.get("items", []) or [])
            marker = data.get("next_marker") or ""
            if not marker:
                break

        if drive_cache is not None:
            drive_cache[cache_key] = items
        return items

    def _ensure_dir(self, token, drive_id, save_dir, drive_cache=None):
        current = "root"
        parts = [part for part in (save_dir or "/").strip("/").split("/") if part]
        for part in parts:
            found = next(
                (
                    item for item in self._list_drive_items(token, drive_id, current, drive_cache)
                    if item.get("name") == part and item.get("type") == "folder"
                ),
                None,
            )
            if found:
                current = found["file_id"]
                continue
            data = self._request(
                "POST",
                "/adrive/v2/file/create",
                headers=self._headers(token),
                json={
                    "drive_id": drive_id,
                    "parent_file_id": current,
                    "name": part,
                    "type": "folder",
                    "check_name_mode": "refuse",
                },
            )
            current = data.get("file_id")
            if not current:
                raise RuntimeError(f"\u521b\u5efa\u963f\u91cc\u4e91\u76d8\u76ee\u5f55\u5931\u8d25: {part}")
            if drive_cache is not None:
                drive_cache.pop((drive_id, data.get("parent_file_id", current)), None)
        return current

    def _ensure_subdir(self, token, drive_id, parent_file_id, rel_dir, drive_cache=None):
        current = parent_file_id
        parts = [part for part in (rel_dir or "").strip("/").split("/") if part]
        for part in parts:
            found = next(
                (
                    item for item in self._list_drive_items(token, drive_id, current, drive_cache)
                    if item.get("name") == part and item.get("type") == "folder"
                ),
                None,
            )
            if found:
                current = found["file_id"]
                continue
            data = self._request(
                "POST",
                "/adrive/v2/file/create",
                headers=self._headers(token),
                json={
                    "drive_id": drive_id,
                    "parent_file_id": current,
                    "name": part,
                    "type": "folder",
                    "check_name_mode": "refuse",
                },
            )
            current = data.get("file_id")
            if not current:
                raise RuntimeError(f"\u521b\u5efa\u963f\u91cc\u4e91\u76d8\u76ee\u5f55\u5931\u8d25: {part}")
            if drive_cache is not None:
                drive_cache.pop((drive_id, data.get("parent_file_id", current)), None)
        return current

    def _flatten_share_files(self, share_id, share_token, share_cache=None):
        files = []
        queue = [("root", "")]
        while queue:
            parent_file_id, prefix = queue.pop(0)
            for item in self._list_share_items(share_id, share_token, parent_file_id, share_cache):
                name = item.get("name") or item.get("file_id")
                rel_path = posixpath.join(prefix, name) if prefix else name
                if item.get("type") == "folder":
                    queue.append((item["file_id"], rel_path))
                else:
                    files.append((item, rel_path))
        return files

    def _existing_names(self, token, drive_id, parent_file_id, existing_cache, drive_cache=None):
        if parent_file_id not in existing_cache:
            existing_cache[parent_file_id] = {
                item.get("name")
                for item in self._list_drive_items(token, drive_id, parent_file_id, drive_cache)
                if item.get("name")
            }
        return existing_cache[parent_file_id]

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

    def _copy_item(self, token, share_token, share_id, item, to_drive_id, to_parent_file_id):
        return self._request(
            "POST",
            "/v2/file/copy",
            headers=self._headers(token, share_token),
            json={
                "share_id": share_id,
                "file_id": item["file_id"],
                "to_drive_id": to_drive_id,
                "to_parent_file_id": to_parent_file_id,
                "auto_rename": False,
            },
        )

    def get_quota(self, account=None):
        token, error = self._current_token(account)
        if error:
            return None
        try:
            data = self._request(
                "POST",
                "/adrive/v1/user/getDriveInfo",
                headers=self._headers(token),
                json={},
            )
            total = data.get("total_size") or data.get("resource_drive_size") or 0
            used = data.get("used_size") or data.get("resource_drive_used_size") or 0
            return {"total": int(total or 0), "used": int(used or 0)}
        except Exception as exc:
            logger.warning(f"\u963f\u91cc\u4e91 quota fetch failed: {exc}")
            return None

    def get_share_folder_name(self, share_url, pwd=None, account=None):
        try:
            share_id = self._extract_share_id(share_url)
            share_pwd = self._extract_passcode(share_url, pwd)
            share_token = self._get_share_token(share_id, share_pwd)
            items = self._list_share_items(share_id, share_token)
            if not items:
                return {"success": False, "error": "\u5206\u4eab\u4e2d\u6ca1\u6709\u53ef\u8f6c\u5b58\u7684\u6587\u4ef6"}
            return {"success": True, "folder_name": items[0].get("name", share_id)}
        except Exception as exc:
            logger.error(f"\u83b7\u53d6\u963f\u91cc\u4e91\u76d8\u5206\u4eab\u4fe1\u606f\u5931\u8d25: {exc}")
            return {"success": False, "error": str(exc)}

    def transfer_share(self, share_url, pwd=None, new_files=None, save_dir=None, progress_callback=None, task_config=None):
        try:
            account = (task_config or {}).get("account")
            token, error = self._current_token(account)
            if error:
                return {"success": False, "error": error}

            share_cache = {}
            drive_cache = {}
            existing_cache = {}

            if progress_callback:
                progress_callback("info", "[\u963f\u91cc\u4e91\u76d8 1/4] \u89e3\u6790\u5206\u4eab\u94fe\u63a5")
            share_id = self._extract_share_id(share_url)
            share_pwd = self._extract_passcode(share_url, pwd)
            share_token = self._get_share_token(share_id, share_pwd)

            if progress_callback:
                progress_callback("info", "[\u963f\u91cc\u4e91\u76d8 2/4] \u83b7\u53d6\u5206\u4eab\u6587\u4ef6\u5217\u8868")
            share_files = self._flatten_share_files(share_id, share_token, share_cache)
            if not share_files:
                return {"success": False, "error": "\u5206\u4eab\u4e2d\u6ca1\u6709\u53ef\u8f6c\u5b58\u7684\u6587\u4ef6"}

            if progress_callback:
                progress_callback("info", "[\u963f\u91cc\u4e91\u76d8 3/4] \u51c6\u5907\u4fdd\u5b58\u76ee\u5f55")
            drive_id = self._get_drive_id(token)
            target_parent = self._ensure_dir(token, drive_id, save_dir or "/", drive_cache)

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
                    token, drive_id, target_parent, rel_dir, drive_cache
                )

            items_to_copy = []
            for item, final_path, rel_dir in candidates:
                file_name = posixpath.basename(final_path)
                copy_parent = parent_by_rel_dir.get(rel_dir or "", target_parent)
                if file_name in self._existing_names(token, drive_id, copy_parent, existing_cache, drive_cache):
                    skipped += 1
                    if progress_callback:
                        skip_path = posixpath.join(save_dir or "/", final_path).replace("\\", "/")
                        progress_callback("info", f"\u6587\u4ef6\u5df2\u5b58\u5728\uff0c\u8df3\u8fc7: {skip_path}")
                    continue
                items_to_copy.append((item, copy_parent, final_path, file_name))

            if not items_to_copy:
                return {
                    "success": True,
                    "message": "\u6ca1\u6709\u65b0\u6587\u4ef6\u9700\u8981\u8f6c\u5b58",
                    "skipped": True,
                    "transferred_files": [],
                    "skipped_count": skipped,
                }

            if progress_callback:
                progress_callback("info", f"[\u963f\u91cc\u4e91\u76d8 4/4] \u8f6c\u5b58 {len(items_to_copy)} \u4e2a\u6587\u4ef6")
            transferred_files = []
            for item, copy_parent, final_path, file_name in items_to_copy:
                self._copy_item(token, share_token, share_id, item, drive_id, copy_parent)
                existing_cache.setdefault(copy_parent, set()).add(file_name)
                transferred_files.append(posixpath.join(save_dir or "/", final_path).replace("\\", "/"))
                if progress_callback:
                    progress_callback("info", f"\u6dfb\u52a0\u6587\u4ef6\uff1a{transferred_files[-1]}")

            return {
                "success": True,
                "message": "\u963f\u91cc\u4e91\u76d8\u8f6c\u5b58\u6210\u529f",
                "skipped": False,
                "transferred_files": transferred_files,
                "skipped_count": skipped,
            }
        except Exception as exc:
            logger.error(f"\u963f\u91cc\u4e91\u76d8\u8f6c\u5b58\u5931\u8d25: {exc}")
            return {"success": False, "error": str(exc)}
