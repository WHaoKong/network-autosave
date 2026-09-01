# -*- coding: utf-8 -*-
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.triggers.cron import CronTrigger
from storage import BaiduStorage
import json
import os
from loguru import logger
import sys
from notify import send as notify_send
from notify import push_config as notify_push_config
from utils import generate_transfer_notification
import time
from threading import Lock, Timer
import pytz
import datetime
import re

class TaskScheduler:
    instance = None
    
    def __init__(self, storage=None):
        self._execution_lock = Lock()
        self.storage = storage or BaiduStorage()
        self.scheduler = None
        self.is_running = False
        
        # 初始化默认调度列
        self.default_schedule = self.storage.config.get('cron', {}).get('default_schedule', [])
        if isinstance(self.default_schedule, str):
            self.default_schedule = [self.default_schedule]
        elif not isinstance(self.default_schedule, list):
            self.default_schedule = []
        
        # 添加通知缓冲区和相关变量
        self._notification_buffer = {
            'success': [],
            'failed': [],
            'skipped': [],
            'transferred_files': {}
        }
        self._notification_lock = Lock()
        self._notification_timer = None
        self._notification_delay = 30  # 延迟30秒发送通知
        
        self._init_scheduler()
        self._init_notify()
        TaskScheduler.instance = self
        
    def _get_current_tasks(self):
        """获取当前的任务列"""
        try:
            # 重新加载配置以获取最新任
            with open('config/config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
            return config['baidu']['tasks']
        except Exception as e:
            logger.error(f"获取任务列表失败: {str(e)}")
            return []

    def update_tasks(self):
        """更新所有任务的调度"""
        try:
            # 清除现有的任务调
            self.scheduler.remove_all_jobs()

            # 系统级作业独立于转存任务，任务列表刷新后必须重新挂载
            self._add_quota_check_job()
            self._add_quark_signin_job()
            
            # 获取任务列表
            tasks = self.storage.list_tasks()
            if not tasks:
                logger.info("没有任务需要调")
                return
            
            # 获取默认调度设置
            default_schedule = self.storage.config.get('cron', {}).get('default_schedule', [])
            if isinstance(default_schedule, str):
                default_schedule = [default_schedule]
            elif not isinstance(default_schedule, list):
                default_schedule = []
            
            custom_count = 0
            default_count = 0
            
            # 添加任务调度
            for task in tasks:
                if task.get('cron'):  # 自定义定时
                    self.add_single_task(task)
                    custom_count += 1
                else:  # 使用默认定时
                    if not default_schedule:
                        logger.warning("存在使用默认定时的任务，但未配置默认定时规则")
                        continue
                    
                    # 为每个默认定时规则添加任
                    for schedule in default_schedule:
                        if schedule and isinstance(schedule, str):  # 确保调度规则有效
                            self.add_single_task(task, schedule)
                            default_count += 1
            
            logger.info(f"任务调度更新完成: {custom_count} 个自定义定时任务, {default_count} 个默认定时任务")
            
        except Exception as e:
            logger.error(f"更新任务调度失败: {str(e)}")

    def start(self):
        """启动调度"""
        try:
            if not self.scheduler:
                self._init_scheduler()
            
            # 直接启动调度器，因为任务已经在_init_scheduler中添
            self.scheduler.start()
            self.is_running = True  # 设置运行状
            logger.success("调度器已启动")
            
            current_time = datetime.datetime.now(pytz.timezone('Asia/Shanghai'))
            logger.info(f"当前时间: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
            
        except Exception as e:
            logger.error(f"启动调度器失: {str(e)}")
            raise

    def _init_scheduler(self):
        """初始化调度器"""
        try:
            if self.scheduler and self.scheduler.running:
                self.scheduler.shutdown(wait=True)
                self.is_running = False  # 重置运行状
            
            #  storage 获取调度器配
            scheduler_config = self.storage.config.get('scheduler', {})
            
            # 使用单线程执行器
            executors = {
                'default': ThreadPoolExecutor(max_workers=scheduler_config.get('max_workers', 1))
            }
            
            # 配置作业存储
            jobstores = {
                'default': MemoryJobStore()
            }
            
            # 配置调度
            job_defaults = {
                'coalesce': scheduler_config.get('coalesce', True),  # 堆积的任务只运行一
                'max_instances': 1,  # 同一个任务同时只能有一个实
                'misfire_grace_time': scheduler_config.get('misfire_grace_time', 3600)  # 错过执行的容错时
            }
            
            # 创建调度
            self.scheduler = BackgroundScheduler(
                executors=executors,
                jobstores=jobstores,
                job_defaults=job_defaults
            )
            self.is_running = False  # 初始化时设置为未运行状
            
            # 获取任务列表
            tasks = self._get_current_tasks() or []
            if not tasks:
                logger.info("没有配置任何任务")
            
            # 获取默认调度并处理多个cron表达
            default_schedule = self.storage.config.get('cron', {}).get('default_schedule', '*/5 * * * *')
            
            # 处理默认调度配置
            cron_expressions = []
            if isinstance(default_schedule, list):
                # 如果是列表格式，直接使用
                schedule_list = default_schedule
            else:
                # 如果是字符串格式，按分号分割
                schedule_list = default_schedule.split(';')
            
            # 验证每个cron表达
            for expr in schedule_list:
                expr = expr.strip()
                if not expr:
                    continue
                # 验证 cron 表达式格
                parts = expr.split()
                if len(parts) == 5:  # 标准 cron 表达式应该有5个字
                    cron_expressions.append(expr)
                else:
                    logger.error(f"无效 cron 表达 ({expr}): 必须包含5个字")
            
            # 保存验证后的默认调度表达
            self.default_schedule = cron_expressions
            
            # 分离自定义定时任务和默认定时任务
            custom_scheduled_tasks = [task for task in tasks if task.get('cron')]
            default_scheduled_tasks = [task for task in tasks if not task.get('cron')]
            
            # 添加自定义定时任务
            for task in custom_scheduled_tasks:
                try:
                    task_order = task.get('order')
                    if not task_order:
                        continue
                        
                    # 使用统一方法解析cron表达
                    self.scheduler.add_job(
                        self._execute_single_task,
                        CronTrigger.from_crontab(convert_cron_weekday(task['cron']), timezone=pytz.timezone('Asia/Shanghai')),
                        args=[task],
                        id=f'task_{task_order - 1}',
                        replace_existing=True
                    )
                    logger.info(f"已添加自定义定时任务: {task.get('name', f'任务{task_order}')} -> {task['cron']}")
                except Exception as e:
                    logger.error(f"添加自定义定时任务失 ({task.get('name', f'任务{task_order}')}): {str(e)}")
            
            # 添加网盘容量检查任务
            self._add_quota_check_job()

            # 添加夸克签到任务
            self._add_quark_signin_job()
            
            # 添加默认定时任务
            if default_scheduled_tasks:
                for task in default_scheduled_tasks:
                    task_order = task.get('order')
                    if not task_order:
                        continue
                        
                    for i, cron_exp in enumerate(cron_expressions):
                        try:
                            self.scheduler.add_job(
                                self._execute_single_task,
                                CronTrigger.from_crontab(convert_cron_weekday(cron_exp), timezone=pytz.timezone('Asia/Shanghai')),
                                args=[task],
                                id=f'task_{task_order - 1}_{i}',
                                replace_existing=True
                            )
                            logger.info(f"已添加默认定时任务: {task.get('name', f'任务{task_order}')} -> {cron_exp}")
                        except Exception as e:
                            logger.error(f"添加默认定时任务失败 ({task.get('name', f'任务{task_order}')}): {str(e)}")
                            continue
            
            logger.info(f"调度器初始化完成: {len(custom_scheduled_tasks)} 个自定义定时任务, {len(default_scheduled_tasks)} 个默认定时任务")
            
        except Exception as e:
            logger.error(f"初始化调度器失败: {str(e)}")
            raise

    def _load_config(self):
        """加载配置文件"""
        try:
            with open('config/config.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载配置文件失败: {str(e)}")
            return None
            
    def _save_config(self):
        """保存配置文件"""
        try:
            with open('config/config.json', 'w', encoding='utf-8') as f:
                json.dump(self.storage.config, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"保存配置文件失败: {str(e)}")

    def _execute_task_group(self, tasks=None):
        """执行任务 - 这是执行默认定时任务的方
        Args:
            tasks: 要执行的任务列表，如果为None则执行所有默认任
        """
        try:
            logger.info(f"=== 开始执行定时任务组 === 时间: {time.strftime('%Y-%m-%d %H:%M:%S')} ===")
            
            results = {
                'success': [],
                'failed': [],
                'skipped': [],
                'transferred_files': {}
            }
            
            # 如果没有指定任务列表，获取所有没有自定义cron的任
            if tasks is None:
                tasks = [t for t in self._get_current_tasks() if not t.get('cron')]
            
            for task in tasks:
                try:
                    task_name = task.get('name', task['url'])
                    logger.info(f"--- 开始处理任务: {task_name} ---")
                    
                    # 用于收集转存的文
                    transferred_files = []
                    
                    def progress_callback(status, msg):
                        logger.info(f"转存进度 - {status}: {msg}")
                        # 从进度消息中提取转存文件信息
                        if status == 'info' and msg.startswith('添加文件:'):
                            # 提取完整的文件路
                            file_path = msg.replace('添加文件:', '').strip()
                            # 保持文件的完整路径结
                            transferred_files.append(file_path)
                    
                    # 执行转存
                    result = self.storage.transfer_share(
                        task['url'],
                        task.get('pwd'),
                        None,
                        task.get('save_dir'),
                        progress_callback,
                        task  # 传入完整的任务配
                    )

                    if result.get('success'):
                        if result.get('skipped'):
                            logger.info(f"任务 {task_name} 无需更新（所有文件已存在")
                            results['skipped'].append(task)
                        else:
                            logger.success(f"任务 {task_name} 执行成功")
                            results['success'].append(task)
                            if transferred_files:
                                # 按目录分组显示文
                                files_by_dir = {}
                                for file_path in transferred_files:
                                    dir_path = os.path.dirname(file_path)
                                    if not dir_path:
                                        dir_path = '/'
                                    files_by_dir.setdefault(dir_path, []).append(os.path.basename(file_path))
                                
                                # 显示分组后的文件
                                for dir_path, files in files_by_dir.items():
                                    logger.info(f"转存 {dir_path}:")
                                    for file in sorted(files):
                                        logger.info(f"  - {file}")
                                
                                results['transferred_files'][task['url']] = transferred_files
                    else:
                        error_msg = result.get('error', '未知错误')
                        logger.error(f"任务 {task_name} 转存失败：{error_msg}")
                        results['failed'].append(task)

                except Exception as e:
                    logger.error(f"执行任务 {task_name} 时发生错: {str(e)}")
                    task['error'] = str(e)
                    results['failed'].append(task)
            
            # 将结果添加到通知缓冲区，而不是立即发送通知
            if results['success'] or results['failed']:
                self._add_to_notification_buffer(results)
            
            logger.info(f"=== 任务组执行完 === 时间: {time.strftime('%Y-%m-%d %H:%M:%S')} ===")
            logger.info(f"成功: {len(results['success'])} , 跳过: {len(results['skipped'])} , 失败: {len(results['failed'])} ")
                
        except Exception as e:
            logger.error(f"执行任务组失: {str(e)}")

    def stop(self):
        """停止调度"""
        try:
            # 取消通知定时
            if self._notification_timer:
                self._notification_timer.cancel()
                self._notification_timer = None
            
            # 发送剩余的通知
            if self._notification_buffer['success'] or self._notification_buffer['failed']:
                self._send_buffered_notification()
            
            if self.scheduler and self.is_running:
                self.scheduler.shutdown()
                self.is_running = False
                logger.info("调度器已停止")
            else:
                logger.info("调度器未在运")
        except Exception as e:
            logger.error(f"停止调度器失: {str(e)}")
        finally:
            self.scheduler = None

    def update_task(self, task_url, cron_exp):
        """更新任务的调度时
        Args:
            task_url: 任务URL
            cron_exp: 新的cron表达
        """
        try:
            # 更新配置文件
            tasks = self.storage.config.get('baidu', {}).get('tasks', [])
            for task in tasks:
                if task.get('url') == task_url:
                    task['cron'] = cron_exp
                    task_order = task.get('order')
                    if task_order:
                        # 使用统一的任务ID格式
                        job_id = f"task_{task_order - 1}"
                        if self.scheduler.get_job(job_id):
                            self.scheduler.reschedule_job(
                                job_id,
                                trigger=CronTrigger.from_crontab(convert_cron_weekday(cron_exp), timezone=pytz.timezone('Asia/Shanghai'))
                            )
                            logger.success(f"已更新任务调: {task_url} -> {cron_exp}")
                    break
            self._save_config()
            
        except Exception as e:
            logger.error(f"更新任务调度失败: {str(e)}")

    def update_default_schedule(self, schedules):
        """更新默认调度规则
        Args:
            schedules: 调度规则列表或字符串(多个规则用分号分)
        """
        try:
            if isinstance(schedules, str):
                schedules = [s.strip() for s in schedules.split(';') if s.strip()]
            
            # 更新本地变量
            self.default_schedule = schedules
            
            # 更新存储中的配置
            if 'cron' not in self.storage.config:
                self.storage.config['cron'] = {}
            self.storage.config['cron']['default_schedule'] = schedules
            self._save_config()
            
            # 重新调度任务
            self.update_tasks()
            logger.info(f"已更新默认调度规: {schedules}")
            return True
        except Exception as e:
            logger.error(f"更新默认调度规则失败: {str(e)}")
            return False

    def remove_task(self, task_url):
        """从调度器中移除任
        Args:
            task_url: 任务URL
        """
        try:
            # 先查找任务的order
            tasks = self.storage.config.get('baidu', {}).get('tasks', [])
            task = next((t for t in tasks if t.get('url') == task_url), None)
            
            if task and task.get('order'):
                task_order = task.get('order')
                base_job_id = f"task_{task_order - 1}"
                
                # 移除主任
                if self.scheduler.get_job(base_job_id):
                    self.scheduler.remove_job(base_job_id)
                
                # 移除可能存在的默认定时任务(带索引)
                for i in range(10):  # 假设最10个默认定
                    job_id = f"{base_job_id}_{i}"
                    if self.scheduler.get_job(job_id):
                        self.scheduler.remove_job(job_id)
                
                logger.success(f"已移除任: {task_url}")
            else:
                logger.warning(f"未找到要移除的任: {task_url}")
        except Exception as e:
            logger.error(f"移除任务失败: {str(e)}")

    def _init_notify(self):
        """初始化通知配置"""
        try:
            notify_config = self.storage.config.get('notify', {})
            if notify_config and notify_config.get('enabled'):
                # 更新推送配
                from notify import push_config, send as notify_send
                
                # 获取通知延迟时间配置
                self._notification_delay = notify_config.get('notification_delay', 30)
                logger.info(f"通知延迟时间设置 {self._notification_delay} ")
                
                # 将通知配置应用到push_config
                # 1. 处理直接字段 (新格)
                if 'direct_fields' in notify_config:
                    for key, value in notify_config.get('direct_fields', {}).items():
                        push_config[key] = value
                    logger.info("已加载直接通知字段配置")
                
                # 2. 处理通道结构 (旧格式，向后兼容)
                elif 'channels' in notify_config:
                    for channel, config in notify_config.get('channels', {}).items():
                        if channel == 'pushplus':
                            # 设置token
                            push_config['PUSH_PLUS_TOKEN'] = config.get('token')
                            # 如果有topic则设置，没有也不影响功能
                            if 'topic' in config:
                                push_config['PUSH_PLUS_USER'] = config.get('topic')
                    logger.info("已加载通道格式的通知配置")
                
                # 3. 处理自定义字 (兼容旧版)
                if 'custom_fields' in notify_config:
                    for key, value in notify_config.get('custom_fields', {}).items():
                        push_config[key] = value
                    logger.info("已加载自定义通知字段配置")
                
                logger.info("通知配置已加载完")
            else:
                logger.debug("通知功能未启用")
        except Exception as e:
            logger.error(f"初始化通知配置失败: {str(e)}")

    def update_notify_config(self, notify_config):
        """更新通知配置"""
        if not self.config:
            self.config = {}
        self.config['notify'] = notify_config
        self._save_config()
        self._init_notify()
        logger.info("通知配置已更")

    def _update_task_status(self, task_url, status, error_msg=''):
        """更新任务状
        Args:
            task_url: 任务URL
            status: 状 (success/failed/skipped)
            error_msg: 错误信息
        """
        try:
            tasks = self.config.get('baidu', {}).get('tasks', [])
            for task in tasks:
                if task['url'] == task_url:
                    task['status'] = status
                    if error_msg:
                        task['error'] = error_msg
                    elif 'error' in task:
                        del task['error']
                    break
            self._save_config()
        except Exception as e:
            logger.error(f"更新任务状态失: {str(e)}")

    def _execute_single_task(self, task):
        """执行单个任务
        Args:
            task: 任务配置
        """
        # 使用锁防止同一任务被并发执
        if not self._execution_lock.acquire(blocking=False):
            logger.warning(f"任务已在执行中，跳过此次执行: {task.get('name', task.get('url', '未知任务'))}")
            return False
            
        try:
            # 获取最新的任务信息，优先使用稳定标识避 order 变化后串任务
            tasks = self.storage.config['baidu']['tasks']
            task_uid = task.get('task_uid') if isinstance(task, dict) else None
            task_order = task.get('order') if isinstance(task, dict) else None

            current_task = self.storage.get_task_by_uid(task_uid)
            if current_task is None and task_order:
                current_task = next((t for t in tasks if t.get('order') == task_order), None)

            if not current_task:
                lookup = f"task_uid={task_uid}" if task_uid else f"order={task_order}"
                logger.error(f"未找到任: {lookup}")
                return False

            task_order = current_task.get('order')
            if not task_order:
                logger.error(f"任务缺少order: {current_task.get('name', current_task.get('url', '未知任务'))}")
                return False
            task_id = task_order - 1  # 转换为前端使用的task_id
            task_name = current_task.get('name', f'任务{task_order}')
            logger.info(f"开始执行任务: {task_name}")
            logger.info(f"分享链接: {current_task.get('url', '')}")
            logger.info(f"保存目录: {current_task.get('save_dir', '')}")
            logger.info(f"提取: {current_task.get('pwd', '')}")
            logger.info("")
            
            # 确保存储实例可用
            if current_task.get('provider', 'baidu') == 'baidu' and not self.storage.is_valid():
                logger.warning("存储实例状态异常，尝试刷新登录状")
                if not self.storage.refresh_login():
                    logger.error("刷新登录状态失")
                    return False

            # 更新结果字典的结
            results = {
                'success': [],
                'failed': [],
                'skipped': [],
                'transferred_files': {}
            }

            # 使用最新的任务信息执行
            def progress_callback(status, message):
                logger.info(f"[{task_name}] {status}: {message}")
                if status == 'info' and message.startswith('添加文件:'):
                    file_path = message.replace('添加文件:', '').strip()
                    if task_id not in results['transferred_files']:
                        results['transferred_files'][task['url']] = []  # 使用 url 作为 key
                    results['transferred_files'][task['url']].append(file_path)

            # 验证必要的任务信
            if not current_task.get('url') or not current_task.get('save_dir'):
                error_msg = "任务缺少必要信息(url或save_dir)"
                logger.error(error_msg)
                self.storage.update_task_status_by_order(task_order, 'failed', error_msg)
                return False

            result = self.storage.transfer_share(
                current_task['url'],
                current_task.get('pwd', ''),  # 使用空字符串作为默认
                None,
                current_task['save_dir'],
                progress_callback,
                current_task  # 传入完整的任务配
            )
            
            # 更新任务状态和结果
            try:
                if result.get('success'):
                    if result.get('skipped'):
                        self.storage.update_task_status_by_order(
                            task_order,
                            'skipped',
                            '没有新文件需要转'
                        )
                    else:
                        self.storage.update_task_status_by_order(
                            task_order,
                            'success',
                            '转存成功',
                            transferred_files=result.get('transferred_files', [])
                        )
                        # 添加到成功列
                        results['success'].append(current_task)
                        # 更新转存文件列表
                        if result.get('transferred_files'):
                            results['transferred_files'][current_task['url']] = result['transferred_files']
                else:
                    self.storage.update_task_status_by_order(
                        task_order,
                        'failed',
                        result.get('error', '转存失败')
                    )
                    current_task['error'] = result.get('error')
                    results['failed'].append(current_task)
                
                # 将结果添加到通知缓冲区，而不是立即发送通知
                if results['success'] or results['failed']:
                    self._add_to_notification_buffer(results)
                
                return result.get('success', False)
                
            except Exception as e:
                logger.error(f"更新任务状态失: {str(e)}")
                return False
            
        except Exception as e:
            logger.error(f"执行任务失败: {str(e)}")
            try:
                self.storage.update_task_status_by_order(task_order, 'failed', str(e))
                # 添加失败通知到缓冲区
                results = {
                    'success': [],
                    'failed': [task],
                    'transferred_files': {}
                }
                self._add_to_notification_buffer(results)
            except:
                pass
            return False
        finally:
            # 释放
            self._execution_lock.release()

    def _add_to_notification_buffer(self, results):
        """将任务结果添加到通知缓冲
        Args:
            results: 任务执行结果
        """
        with self._notification_lock:
            # 合并成功任务
            self._notification_buffer['success'].extend(results['success'])
            
            # 合并失败任务
            self._notification_buffer['failed'].extend(results['failed'])
            
            # 合并跳过任务
            self._notification_buffer['skipped'].extend(results.get('skipped', []))
            
            # 合并转存文件
            for url, files in results['transferred_files'].items():
                if url not in self._notification_buffer['transferred_files']:
                    self._notification_buffer['transferred_files'][url] = []
                self._notification_buffer['transferred_files'][url].extend(files)
            
            # 取消现有的定时器
            if self._notification_timer:
                self._notification_timer.cancel()
            
            # 创建新的定时器，延迟发送通知
            self._notification_timer = Timer(self._notification_delay, self._send_buffered_notification)
            self._notification_timer.daemon = True  # 设置为守护线程，避免阻止程序退
            self._notification_timer.start()
            
            logger.info(f"已将任务结果添加到通知缓冲区，将在 {self._notification_delay} 秒后发送通知")

    def _send_buffered_notification(self):
        """发送缓冲区中的通知"""
        with self._notification_lock:
            if not (self._notification_buffer['success'] or self._notification_buffer['failed']):
                logger.info("通知缓冲区为空，无需发送通知")
                return
            
            try:
                notification_content = generate_transfer_notification(self._notification_buffer)
                if notification_content.strip():  # 只在有内容时发送通知
                    logger.info(f"准备发送汇总通知:\n{notification_content}")
                    notify_send("百度网盘自动追更", notification_content)
                    logger.info(f"通知发送成功， {len(self._notification_buffer['success'])} 个成功任务，{len(self._notification_buffer['failed'])} 个失败任")
                else:
                    logger.warning("生成的通知内容为空，跳过发")
            except Exception as e:
                logger.error(f"发送汇总通知失败: {str(e)}")
            finally:
                # 清空缓冲
                self._notification_buffer = {
                    'success': [],
                    'failed': [],
                    'skipped': [],
                    'transferred_files': {}
                }
                self._notification_timer = None

    def _resolve_task_reference(self, task_ref):
        """ task_uid/order/url 解析任务，兼容旧调用"""
        current_task = self.storage.resolve_task(task_ref)
        if current_task is not None:
            return current_task

        if isinstance(task_ref, dict):
            return None

        return self.storage.resolve_task(url=task_ref)

    def update_task_schedule(self, task_ref, cron_exp=None):
        """更新任务调度"""
        try:
            current_task = self._resolve_task_reference(task_ref)

            if not current_task:
                logger.error(f"未找到任: {task_ref}")
                return False

            task_order = current_task.get('order')
            if not task_order:
                logger.error(f"任务缺少order: {current_task.get('task_uid') or current_task.get('url')}")
                return False

            task_id = f'task_{task_order - 1}'  # 转换为前端使用的task_id

            # 移除旧任
            if self.scheduler.get_job(task_id):
                self.scheduler.remove_job(task_id)

            # 使用新的cron表达式或保持原
            final_cron = cron_exp if cron_exp is not None else current_task.get('cron')

            if final_cron:
                try:
                    self.scheduler.add_job(
                        self._execute_single_task,
                        CronTrigger.from_crontab(convert_cron_weekday(final_cron)),
                        args=[current_task],
                        id=task_id,
                        replace_existing=True
                    )
                    logger.info(
                        f"已更新任务调: {current_task.get('task_uid', current_task.get('url'))} "
                        f"(task_id={task_order}) -> {final_cron}"
                    )
                except Exception as e:
                    logger.error(f"更新任务调度失败: {str(e)}")
                    return False
            else:
                logger.info(
                    f"任务 {current_task.get('task_uid', current_task.get('url'))} 切换到默认定时，正在更新调度..."
                )
                self.update_tasks()  # 重新加载所有任务的调度

            return True

        except Exception as e:
            logger.error(f"更新任务调度失败: {str(e)}")
            return False

    def sync_task_info(self, task_ref):
        """同步任务信息
        Args:
            task_ref: 任务引用（优 task_uid，兼 URL/order/任务对象
        Returns:
            bool: 是否成功
        """
        try:
            current_task = self._resolve_task_reference(task_ref)

            if not current_task:
                logger.error(f"未找到任: {task_ref}")
                return False

            # 更新任务调度
            return self.update_task_schedule(current_task, current_task.get('cron'))

        except Exception as e:
            logger.error(f"同步任务信息失败: {str(e)}")
            return False

    def add_single_task(self, task, schedule=None):
        """添加单个任务的调
        Args:
            task: 任务配置
            schedule: 可选的定时规则，用于默认定
        """
        try:
            cron_schedule = schedule or task.get('cron')
            if not cron_schedule:
                return
                
            task_order = task.get('order')
            if not task_order:
                logger.error(f"任务缺少order: {task.get('name', task.get('url', '未知任务'))}")
                return
                
            task_id = task_order - 1
            
            try:
                # 使用统一方法解析cron表达
                trigger = CronTrigger.from_crontab(convert_cron_weekday(cron_schedule), timezone=pytz.timezone('Asia/Shanghai'))

                # 为默认定时任务添加索
                job_id = f'task_{task_id}'
                if schedule:  # 使用默认定时
                    # 查找已有的默认定时任务数
                    count = 0
                    while self.scheduler.get_job(f'{job_id}_{count}'):
                        count += 1
                    job_id = f'{job_id}_{count}'
                
                self.scheduler.add_job(
                    self._execute_single_task,
                    trigger,
                    args=[task],
                    id=job_id,
                    replace_existing=True
                )
                
                # 根据schedule参数判断是默认定时还是自定义定时
                schedule_type = "默认定时" if schedule else "自定义定时"
                logger.info(f"已添加{schedule_type}任务: {task.get('name', task.get('url', f'任务{task_order}'))}, 调度: {cron_schedule}")
            except Exception as e:
                logger.error(f"解析cron表达式失 '{cron_schedule}': {str(e)}")
        except Exception as e:
            logger.error(f"添加任务调度失败 ({task.get('name', task.get('url', '未知任务'))}): {str(e)}")

    def _add_quota_check_job(self):
        """添加网盘容量检查任务"""
        try:
            # 获取容量检查配
            quota_alert = self.storage.config.get('quota_alert', {})
            if not quota_alert.get('enabled', False):
                logger.info("网盘容量检查功能未启用")
                return
            
            # 获取检查时间表达式，默认每00:00
            check_schedule = quota_alert.get('check_schedule', '0 0 * * *')
            
            # 添加定时任务
            self.scheduler.add_job(
                self._check_disk_quota,
                CronTrigger.from_crontab(convert_cron_weekday(check_schedule), timezone=pytz.timezone('Asia/Shanghai')),
                id='quota_check',
                replace_existing=True
            )
            logger.info(f"已添加网盘容量检查任务: {check_schedule}")
        except Exception as e:
            logger.error(f"添加网盘容量检查任务失: {str(e)}")

    def _add_quark_signin_job(self):
        """添加夸克网盘每日签到任务。"""
        try:
            signin_config = self.storage.config.get('quark_signin', {})
            if not signin_config.get('enabled', False):
                logger.info("夸克自动签到功能未启用")
                return

            schedule = signin_config.get('schedule', '0 8 * * *')
            self.scheduler.add_job(
                self._run_quark_signins,
                CronTrigger.from_crontab(
                    convert_cron_weekday(schedule),
                    timezone=pytz.timezone('Asia/Shanghai')
                ),
                id='quark_signin',
                replace_existing=True,
                coalesce=True,
                max_instances=1
            )
            logger.info(f"已添加夸克签到任务: {schedule}")
        except Exception as exc:
            logger.error(f"添加夸克签到任务失败: {exc}")

    def _run_quark_signins(self):
        """串行执行所有已启用账号的夸克签到。"""
        try:
            results = self.storage.quark_storage.run_enabled_signins()
            if not results:
                logger.info("没有启用自动签到的夸克账号")
                return []

            lines = []
            for result in results:
                account = result.get('account', 'unknown')
                reward_mb = round(result.get('reward_bytes', 0) / (1024 ** 2), 2)
                if result.get('success'):
                    detail = result.get('message', '签到成功')
                    if reward_mb:
                        detail += f"，奖励 {reward_mb} MB"
                    logger.info(f"夸克账号 {account}: {detail}")
                else:
                    detail = result.get('message', '签到失败')
                    logger.warning(f"夸克账号 {account}: {detail}")
                lines.append(f"- {account}: {detail}")

            signin_config = self.storage.config.get('quark_signin', {})
            notify_enabled = self.storage.config.get('notify', {}).get('enabled', False)
            if signin_config.get('notify', True) and notify_enabled:
                notify_send("夸克每日签到", "\n".join(lines))

            return results
        except Exception as exc:
            logger.exception(f"执行夸克自动签到失败: {exc}")
            return []

    def _check_disk_quota(self):
        """检查网盘容量并发送通知"""
        try:
            logger.info("开始检查网盘容")
            
            # 确保存储对象有效
            if not self.storage or not self.storage.is_valid():
                logger.error("存储对象无效或未登录")
                return
            
            # 获取用户信息和配
            user_info = self.storage.get_user_info()
            if not user_info or 'quota' not in user_info:
                logger.error("无法获取用户配额信息")
                return
            
            # 获取配额信息
            quota = user_info['quota']
            total = quota.get('total', 0)
            used = quota.get('used', 0)
            
            if total <= 0:
                logger.error("获取到的总容量为0，无法计算使用比")
                return
            
            # 计算使用比例
            used_percent = round(used / total * 100, 2)
            
            # 转换为GB并保2位小
            total_gb = round(total / (1024**3), 2)
            used_gb = round(used / (1024**3), 2)
            
            # 获取阈
            quota_alert = self.storage.config.get('quota_alert', {})
            threshold = quota_alert.get('threshold_percent', 90)
            
            # 记录日志
            logger.info(f"网盘容量检: 已使 {used_gb}GB/{total_gb}GB ({used_percent}%), 阈: {threshold}%")
            
            # 检查是否超过阈
            if used_percent >= threshold:
                # 获取用户
                username = user_info.get('user_name', self.storage.config['baidu'].get('current_user', '未知用户'))
                
                # 构建通知内容
                title = f"网盘容量不足 - {username}"
                content = f"""
## 网盘容量不足

**用户**: {username}  
**已使**: {used_gb}GB / {total_gb}GB  
**使用比例**: {used_percent}%  
**警告阈**: {threshold}%  

您的百度网盘空间使用量已超过设定阈值，请及时清理不必要的文件，以免影响正常使用
"""
                
                # 直接发送容量警告通知，不使用缓冲
                # 因为容量警告是独立的重要通知，不应与普通任务通知合并
                notify_send(title, content)
                logger.warning(f"已发送网盘容量警告通知: {used_percent}% >= {threshold}%")
            else:
                logger.info(f"网盘容量正常: {used_percent}% < {threshold}%")
                
        except Exception as e:
            logger.error(f"检查网盘容量失: {str(e)}")

def convert_cron_weekday(cron_exp):
    """
    转换cron表达式中的星期几字段，适配APScheduler的映射规
    标准cron: 07=周日, 1=周一, ..., 6=周六
    APScheduler: 0=周一, 1=周二, ..., 6=周日
    
    转换规则:
    - 使用英文简 (sun, mon, tue, wed, thu, fri, sat) 不变
    - 数字 0 转为 6 (周日)
    - 数字 7 转为 6 (周日)
    - 数字 1-6 转为 0-5 (周一到周六，1)
    """
    if not cron_exp or not isinstance(cron_exp, str):
        return cron_exp
        
    parts = cron_exp.strip().split()
    if len(parts) != 5:  # 标准cron表达式有5个字
        return cron_exp
        
    dow_field = parts[4]  # 5个字段是星期 (0-7)
    
    # 如果包含英文简写，不做转换
    if re.search(r'[a-zA-Z]', dow_field):
        return cron_exp
    
    # 处理复杂表达 (例如: 1-5,0  */2)
    new_dow = []
    for item in dow_field.split(','):
        if '/' in item:  # 处理 */2 这样的格
            interval_parts = item.split('/')
            if interval_parts[0] == '*':
                new_dow.append(item)  # 保持不变
            else:
                # 这里可能需要更复杂的处理，暂时保持不变
                new_dow.append(item)
        elif '-' in item:  # 处理 1-5 这样的范
            range_parts = item.split('-')
            start = int(range_parts[0])
            end = int(range_parts[1])
            # 转换范围边界
            if start == 0 or start == 7:  # 07都表示周
                start = 6  # APScheduler6表示周日
            else:
                start = start - 1  # 其他天减1
                
            if end == 0 or end == 7:  # 07都表示周
                end = 6  # APScheduler6表示周日
            else:
                end = end - 1  # 其他天减1
                
            new_dow.append(f"{start}-{end}")
        else:  # 处理单个数字
            try:
                day = int(item)
                if day == 0 or day == 7:  # 07都表示周
                    new_dow.append('6')  # APScheduler6表示周日
                else:
                    new_dow.append(str(day - 1))  # 其他天减1
            except ValueError:
                new_dow.append(item)  # 非数字，保持不变
    
    # 替换原表达式中的星期几字
    parts[4] = ','.join(new_dow)
    return ' '.join(parts)

def main():
    """命令行入"""
    import argparse
    import time
    
    parser = argparse.ArgumentParser(description='定时任务管理工具')
    parser.add_argument('action', choices=['start', 'stop', 'update-task', 'update-default'],
                       help='要执行的操作')
    parser.add_argument('--cron', help='新的cron表达')
    parser.add_argument('--url', help='要更新的任务URL')
    
    args = parser.parse_args()
    scheduler = TaskScheduler()
    
    if args.action == 'start':
        scheduler.start()
        try:
            # 保持程序运行
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            scheduler.stop()
    elif args.action == 'stop':
        scheduler.stop()
    elif args.action == 'update-task':
        if not args.url or not args.cron:
            logger.error("更新任务需要提供任务URL和新的cron表达")
            return
        scheduler.update_task(args.url, args.cron)
    elif args.action == 'update-default':
        if not args.cron:
            logger.error("更新默认调度需要提供新的cron表达")
            return
        scheduler.update_default_schedule(args.cron)

if __name__ == '__main__':
    main() 