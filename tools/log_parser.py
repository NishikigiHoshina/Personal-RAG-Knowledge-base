#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
日志解析工具：读取文件夹下所有 .log 文件，按 UID 匹配日志条目
"""

import os
import re
import json
import glob
import argparse
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import List, Optional, Iterator
from pathlib import Path


@dataclass
class LogEntry:
    """单条日志记录"""
    timestamp: str           # 原始时间字符串
    datetime_obj: datetime   # 解析后的 datetime 对象
    level: str              # 日志级别 (INFO/DEBUG/WARNING/ERROR)
    logger: str             # 记录器名称 (agent)
    file_info: str          # 文件和行号 (middleware.py:46)
    tag: str                # 方括号标签 [log_before_model]
    message: str            # 日志正文内容
    uid: Optional[str]      # 提取的 uid (如 LC12808)
    raw_line: str           # 原始行内容
    
    def to_dict(self) -> dict:
        d = asdict(self)
        d['datetime_obj'] = self.datetime_obj.isoformat()
        return d


class LogParser:
    """日志解析器"""
    
    # 正则匹配日志格式：
    # 2026-08-06 13:47:02,000 - agent - INFO - middleware.py:46 - [log_before_model]即将调用模型...
    LOG_PATTERN = re.compile(
        r'^(?P<timestamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3})\s+-\s+'
        r'(?P<logger>\w+)\s+-\s+'
        r'(?P<level>\w+)\s+-\s+'
        r'(?P<file_info>[\w\./]+:\d+)\s+-\s+'
        r'(?P<tag>\[[^\]]+\])'
        r'(?P<message>.*)$'
    )
    
    # 提取 uid:xxx 或 uid=xxx
    UID_PATTERN = re.compile(r'(?:^|\s)uid[:=](?P<uid>\w+)(?:\s|$)', re.IGNORECASE)
    
    def parse_line(self, line: str) -> Optional[LogEntry]:
        """解析单行日志"""
        line = line.rstrip('\n').rstrip('\r')
        if not line.strip():
            return None
            
        match = self.LOG_PATTERN.match(line)
        if not match:
            return None  # 不匹配标准格式的行，可忽略或作为原始行处理
            
        data = match.groupdict()
        timestamp_str = data['timestamp']
        
        # 解析时间 2026-08-06 13:47:02,000
        try:
            dt = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
        except ValueError:
            dt = None
            
        # 提取 UID
        uid_match = self.UID_PATTERN.search(line)
        uid = uid_match.group('uid') if uid_match else None
        
        # 清理 message 中的 uid 后缀，使 message 更干净（可选）
        message = data['message'].strip()
        
        return LogEntry(
            timestamp=timestamp_str,
            datetime_obj=dt,
            level=data['level'],
            logger=data['logger'],
            file_info=data['file_info'],
            tag=data['tag'],
            message=message,
            uid=uid,
            raw_line=line
        )
    
    def parse_file(self, filepath: str) -> Iterator[LogEntry]:
        """解析单个日志文件"""
        path = Path(filepath)
        if not path.exists():
            print(f"[警告] 文件不存在: {filepath}")
            return
            
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    entry = self.parse_line(line)
                    if entry:
                        yield entry
        except UnicodeDecodeError:
            # 尝试 GBK 编码
            with open(path, 'r', encoding='gbk', errors='replace') as f:
                for line_num, line in enumerate(f, 1):
                    entry = self.parse_line(line)
                    if entry:
                        yield entry
        except Exception as e:
            print(f"[错误] 读取文件失败 {filepath}: {e}")


class LogSearcher:
    """日志检索器"""
    
    def __init__(self, log_dir: str):
        self.log_dir = Path(log_dir)
        self.parser = LogParser()
        
    def find_log_files(self) -> List[str]:
        """查找所有 .log 文件（支持子目录递归）"""
        if not self.log_dir.exists():
            raise FileNotFoundError(f"日志目录不存在: {self.log_dir}")
            
        # 递归查找所有 .log 文件
        log_files = sorted(self.log_dir.rglob('*.log'))
        return [str(f) for f in log_files]
    
    def search_by_uid(
        self, 
        uid: str, 
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        include_context: bool = False
    ) -> List[LogEntry]:
        """
        按 UID 搜索日志
        
        Args:
            uid: 要匹配的用户 ID
            start_time: 可选，起始时间
            end_time: 可选，结束时间
            include_context: 是否包含该 UID 前后相邻的无 UID 日志（用于还原完整会话）
        """
        results = []
        log_files = self.find_log_files()
        
        print(f"[*] 发现 {len(log_files)} 个日志文件")
        
        for filepath in log_files:
            print(f"[*] 正在解析: {filepath}")
            file_entries = list(self.parser.parse_file(filepath))
            
            if include_context:
                # 如果启用上下文模式，先标记哪些行属于该 UID 的会话
                results.extend(
                    self._extract_with_context(file_entries, uid, start_time, end_time)
                )
            else:
                # 仅匹配带该 UID 的行
                for entry in file_entries:
                    if entry.uid == uid:
                        if self._time_in_range(entry, start_time, end_time):
                            results.append(entry)
                            
        # 按时间排序
        results.sort(key=lambda x: x.datetime_obj or datetime.min)
        return results
    
    def _extract_with_context(
        self, 
        entries: List[LogEntry], 
        uid: str,
        start_time: Optional[datetime],
        end_time: Optional[datetime]
    ) -> List[LogEntry]:
        """提取带目标 UID 的行及其前后相邻行（同一会话上下文）"""
        matched_indices = set()
        
        for i, entry in enumerate(entries):
            if entry.uid == uid and self._time_in_range(entry, start_time, end_time):
                matched_indices.add(i)
                # 向前向后各取 2 行作为上下文
                for j in range(max(0, i-2), min(len(entries), i+3)):
                    matched_indices.add(j)
                    
        return [entries[i] for i in sorted(matched_indices)]
    
    def _time_in_range(
        self, 
        entry: LogEntry, 
        start: Optional[datetime], 
        end: Optional[datetime]
    ) -> bool:
        """检查时间是否在范围内"""
        if entry.datetime_obj is None:
            return True  # 时间解析失败，默认保留
        if start and entry.datetime_obj < start:
            return False
        if end and entry.datetime_obj > end:
            return False
        return True
    
    def export_results(self, entries: List[LogEntry], output_path: str, format: str = 'json'):
        """导出结果"""
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        
        if format == 'json':
            data = [e.to_dict() for e in entries]
            with open(output, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"[✓] 已导出 JSON: {output}")
            
        elif format == 'txt':
            with open(output, 'w', encoding='utf-8') as f:
                for e in entries:
                    f.write(e.raw_line + '\n')
            print(f"[✓] 已导出 TXT: {output}")
            
        elif format == 'csv':
            import csv
            with open(output, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['timestamp', 'level', 'uid', 'tag', 'message', 'file_info'])
                for e in entries:
                    writer.writerow([
                        e.timestamp, e.level, e.uid or '',
                        e.tag, e.message, e.file_info
                    ])
            print(f"[✓] 已导出 CSV: {output}")


def main():
    parser = argparse.ArgumentParser(description='日志 UID 检索工具')
    parser.add_argument('log_dir', help='日志文件夹路径')
    parser.add_argument('--uid', '-u', required=True, help='要检索的 UID')
    parser.add_argument('--output', '-o', help='输出文件路径')
    parser.add_argument('--format', '-f', choices=['json', 'txt', 'csv'], default='txt',
                       help='输出格式 (默认: txt)')
    parser.add_argument('--start', help='起始时间 (格式: 2026-08-06 14:00:00)')
    parser.add_argument('--end', help='结束时间 (格式: 2026-08-06 15:00:00)')
    parser.add_argument('--context', '-c', action='store_true',
                       help='包含相邻上下文日志（还原完整会话）')
    
    args = parser.parse_args()
    
    # 解析时间参数
    start_time = datetime.strptime(args.start, '%Y-%m-%d %H:%M:%S') if args.start else None
    end_time = datetime.strptime(args.end, '%Y-%m-%d %H:%M:%S') if args.end else None
    
    # 执行搜索
    searcher = LogSearcher(args.log_dir)
    results = searcher.search_by_uid(
        uid=args.uid,
        start_time=start_time,
        end_time=end_time,
        include_context=args.context
    )
    
    print(f"\n[✓] 共匹配到 {len(results)} 条日志记录 (UID: {args.uid})")
    
    # 打印结果摘要
    for entry in results[:20]:  # 最多显示前20条
        uid_str = f" [uid:{entry.uid}]" if entry.uid else ""
        print(f"{entry.timestamp} | {entry.level:5} | {entry.tag:20} | {entry.message[:60]}{uid_str}")
        
    if len(results) > 20:
        print(f"... 还有 {len(results)-20} 条记录未显示")
    
    # 导出
    if args.output:
        searcher.export_results(results, args.output, args.format)
    else:
        # 默认导出到当前目录
        default_output = f"uid_{args.uid}_logs.{args.format}"
        searcher.export_results(results, default_output, args.format)


# ========== 无命令行调用方式（直接 import 使用） ==========

def search_logs_simple(log_dir: str, uid: str) -> List[dict]:
    """
    简单调用方式，直接返回字典列表
    """
    searcher = LogSearcher(log_dir)
    entries = searcher.search_by_uid(uid=uid)
    return [e.to_dict() for e in entries]


if __name__ == '__main__':
    main()