"""
Report Service - File system based report management
"""
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class ReportService:
    """Report service - scan and manage reports from file system"""
    
    # Root directory for all reports
    REPORT_ROOT = Path("G:/report")
    
    def __init__(self):
        self.root = self.REPORT_ROOT
        self._ensure_root_exists()
    
    def _ensure_root_exists(self):
        """Ensure report root directory exists"""
        if not self.root.exists():
            logger.warning(f"Report root directory does not exist: {self.root}")
    
    # 支持的文档格式
    SUPPORTED_EXTENSIONS = ['.pdf', '.epub', '.html', '.md', '.docx', '.sql', '.txt']
    
    def get_report_types(self) -> List[Dict]:
        """
        Get all report types (subdirectories in root)
        
        Returns:
            List of report type info dicts
        """
        types = []
        
        if not self.root.exists():
            return types
        
        for item in sorted(self.root.iterdir()):
            if item.is_dir():
                # Count all supported document files in this directory
                doc_count = 0
                for ext in self.SUPPORTED_EXTENSIONS:
                    doc_count += len(list(item.glob(f"*{ext}")))
                
                types.append({
                    "code": item.name,
                    "name": item.name,
                    "path": str(item),
                    "count": doc_count
                })
        
        return types
    
    def get_reports_by_type(self, report_type: str, sub_path: str = '') -> List[Dict]:
        """
        Get all reports for a specific type, supports sub-directory browsing
        
        Args:
            report_type: Report type code (directory name)
            sub_path: Sub-directory path (e.g. '01-需求与设计/功能需求设计')
            
        Returns:
            List of report info dicts (directories first, then files)
        """
        reports = []
        type_dir = self.root / report_type
        if sub_path:
            type_dir = type_dir / sub_path
        
        if not type_dir.exists() or not type_dir.is_dir():
            return reports
        
        # 【新增】先列出子目录
        for item in sorted(type_dir.iterdir()):
            if item.is_dir() and not item.name.startswith('.') and not item.name.startswith('__'):
                # 统计子目录中的文件数
                file_count = sum(1 for f in item.rglob('*') 
                               if f.is_file() and f.suffix.lower() in self.SUPPORTED_EXTENSIONS)
                rel_path = str(item.relative_to(self.root / report_type)).replace('\\', '/')
                reports.append({
                    "id": f"{report_type}/{rel_path}",
                    "name": item.name,
                    "filename": item.name,
                    "type": report_type,
                    "format": "directory",
                    "format_icon": "📁",
                    "path": str(item),
                    "relative_path": rel_path,
                    "size": 0,
                    "size_formatted": f"{file_count}个文件",
                    "modified_time": datetime.fromtimestamp(item.stat().st_mtime).isoformat(),
                    "modified_time_formatted": datetime.fromtimestamp(item.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
                    "is_directory": True,
                    "file_count": file_count
                })
        
        # 收集当前目录下的文件
        all_files = []
        for ext in self.SUPPORTED_EXTENSIONS:
            all_files.extend(type_dir.glob(f"*{ext}"))
        
        # 按修改时间排序
        for doc_file in sorted(all_files, key=lambda x: x.stat().st_mtime, reverse=True):
            stat = doc_file.stat()
            # 根据文件类型显示不同的图标
            ext_lower = doc_file.suffix.lower()
            if ext_lower == '.pdf':
                file_type_icon = "📄"
            elif ext_lower == '.md':
                file_type_icon = "📝"
            elif ext_lower == '.docx':
                file_type_icon = "📋"
            elif ext_lower == '.sql':
                file_type_icon = "🗃️"
            else:
                file_type_icon = "📖"
            
            rel_path = str(doc_file.relative_to(self.root / report_type)).replace('\\', '/')
            reports.append({
                "id": f"{report_type}/{rel_path}",
                "name": doc_file.stem,
                "filename": doc_file.name,
                "type": report_type,
                "format": ext_lower.replace('.', ''),
                "format_icon": file_type_icon,
                "path": str(doc_file),
                "relative_path": rel_path,
                "size": stat.st_size,
                "size_formatted": self._format_size(stat.st_size),
                "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "modified_time_formatted": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "is_directory": False
            })
        
        return reports
    
    def get_report(self, report_type: str, filename: str) -> Optional[Dict]:
        """
        Get single report info
        
        Args:
            report_type: Report type code
            filename: PDF filename
            
        Returns:
            Report info dict or None
        """
        report_path = self.root / report_type / filename
        
        if not report_path.exists() or not report_path.is_file():
            return None
        
        stat = report_path.stat()
        return {
            "id": f"{report_type}/{filename}",
            "name": report_path.stem,
            "filename": filename,
            "type": report_type,
            "path": str(report_path),
            "relative_path": f"{report_type}/{filename}",
            "size": stat.st_size,
            "size_formatted": self._format_size(stat.st_size),
            "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "modified_time_formatted": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
        }
    
    def get_report_file_path(self, report_type: str, filename: str) -> Optional[Path]:
        """
        Get absolute path to report file
        
        Args:
            report_type: Report type code
            filename: PDF filename
            
        Returns:
            Path object or None if not found
        """
        file_path = self.root / report_type / filename
        
        if file_path.exists() and file_path.is_file():
            return file_path
        
        return None
    
    def _format_size(self, size_bytes: int) -> str:
        """Format file size to human readable"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"
    
    def search_reports(self, keyword: str) -> List[Dict]:
        """
        Search reports by keyword - recursively traverses all directories
        
        Args:
            keyword: Search keyword (matched against filename)
            
        Returns:
            List of matching report info dicts with directory path info
        """
        results = []
        keyword_lower = keyword.lower()
        
        for report_type in self.get_report_types():
            type_code = report_type["code"]
            type_name = report_type["name"]
            type_dir = self.root / type_code
            
            if not type_dir.exists() or not type_dir.is_dir():
                continue
            
            # 递归遍历所有文件
            for doc_file in type_dir.rglob('*'):
                if not doc_file.is_file():
                    continue
                if doc_file.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
                    continue
                if doc_file.name.startswith('.') or doc_file.name.startswith('__'):
                    continue
                if keyword_lower not in doc_file.name.lower():
                    continue
                
                # 计算相对路径
                rel_path = doc_file.relative_to(type_dir)
                parent_path = str(rel_path.parent).replace('\\', '/')
                if parent_path == '.':
                    parent_path = ''
                
                # 文件图标
                ext_lower = doc_file.suffix.lower()
                if ext_lower == '.pdf':
                    file_type_icon = "📄"
                elif ext_lower == '.md':
                    file_type_icon = "📝"
                elif ext_lower == '.docx':
                    file_type_icon = "📋"
                elif ext_lower == '.sql':
                    file_type_icon = "🗃️"
                else:
                    file_type_icon = "📖"
                
                stat = doc_file.stat()
                full_rel_path = str(rel_path).replace('\\', '/')
                
                results.append({
                    "id": f"{type_code}/{full_rel_path}",
                    "name": doc_file.stem,
                    "filename": doc_file.name,
                    "type": type_code,
                    "type_name": type_name,
                    "format": ext_lower.replace('.', ''),
                    "format_icon": file_type_icon,
                    "path": str(doc_file),
                    "relative_path": full_rel_path,
                    "parent_path": parent_path,
                    "display_path": f"{type_name}/{parent_path}" if parent_path else type_name,
                    "size": stat.st_size,
                    "size_formatted": self._format_size(stat.st_size),
                    "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "modified_time_formatted": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                    "is_directory": False
                })
        
        # 按目录路径排序
        results.sort(key=lambda x: (x['type'], x['parent_path'], x['name']))
        return results
