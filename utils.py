import os
from loguru import logger


def _task_display_name(task):
    return (task.get('name') or task.get('url') or '未命名任务').strip()


def generate_transfer_notification_title(tasks_results, default_title="网盘自动转存"):
    """生成通知标题：任务名称 + 成功/失败，便于在卡片上一眼看出结果。"""
    try:
        parts = []
        transferred_files = tasks_results.get('transferred_files') or {}

        for task in tasks_results.get('success') or []:
            if transferred_files.get(task.get('url')):
                parts.append(f"{_task_display_name(task)} 成功")

        for task in tasks_results.get('failed') or []:
            parts.append(f"{_task_display_name(task)} 失败")

        return "；".join(parts) if parts else default_title
    except Exception as e:
        logger.error(f"生成通知标题失败: {str(e)}")
        return default_title


def generate_transfer_notification(tasks_results):
    """生成转存通知内容"""
    try:
        content = []
        
        # 添加成功任务信息
        for task in tasks_results['success']:
            task_name = task.get('name', task['url'])
            save_dir = task.get('save_dir', '')
            transferred_files = tasks_results['transferred_files'].get(task['url'], [])
            
            if transferred_files:  # 只有在有新文件时才添加到通知
                content.append(f"✅《{task_name}》添加追更：")
                
                # 按目录分组文件
                files_by_dir = {}
                for file_path in transferred_files:
                    dir_path = os.path.dirname(file_path)
                    if not dir_path:
                        dir_path = '/'
                    files_by_dir.setdefault(dir_path, []).append(os.path.basename(file_path))
                
                # 对每个目录的文件进行排序和显示
                for dir_path, files in files_by_dir.items():
                    # 构建完整的保存路径
                    full_path = save_dir
                    if dir_path and dir_path != '/':
                        full_path = os.path.join(save_dir, dir_path).replace('\\', '/')
                    content.append(full_path)
                    
                    files.sort()  # 对文件名进行排序
                    for i, file in enumerate(files):
                        is_last = (i == len(files) - 1)
                        prefix = '└── ' if is_last else '├── '
                        
                        # 根据文件类型添加图标
                        if file.lower().endswith(('.mp4', '.mkv', '.avi', '.mov')):
                            icon = '🎞️'
                        elif '.' not in file:
                            icon = '📁'
                        else:
                            icon = '📄'
                            
                        content.append(f"{prefix}{icon}{file}")
                
                content.append("")  # 添加空行分隔任务
        
        # 添加失败任务信息
        for task in tasks_results['failed']:
            task_name = task.get('name', task['url'])
            error_msg = task.get('error', '未知错误')
            if "error_code: 115" in error_msg:
                content.append(f"❌《{task_name}》：分享链接已失效")
            else:
                content.append(f"❌《{task_name}》：{error_msg}")
            content.append("")  # 添加空行分隔任务
        
        return "\n".join(content)
    except Exception as e:
        logger.error(f"生成通知内容失败: {str(e)}")
        return "生成通知内容失败" 