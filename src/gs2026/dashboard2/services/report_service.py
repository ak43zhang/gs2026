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
                # Count PDF files in this directory
                pdf_count = len(list(item.glob("*.pdf")))
                
                types.append({
                    "code": item.name,
                    "name": item.name,
                    "path": str(item),
                    "count": pdf_count
                })
        
        return types
    
    def get_reports_by_type(self, report_type: str) -> List[Dict]:
        """
        Get all reports for a specific type
        
        Args:
            report_type: Report type code (directory name)
            
        Returns:
            List of report info dicts
        """
        reports = []
        type_dir = self.root / report_type
        
        if not type_dir.exists() or not type_dir.is_dir():
            return reports
        
        for pdf_file in sorted(type_dir.glob("*.pdf"), key=lambda x: x.stat().st_mtime, reverse=True):
            stat = pdf_file.stat()
            reports.append({
                "id": f"{report_type}/{pdf_file.name}",
                "name": pdf_file.stem,
                "filename": pdf_file.name,
                "type": report_type,
                "path": str(pdf_file),
                "relative_path": f"{report_type}/{pdf_file.name}",
                "size": stat.st_size,
                "size_formatted": self._format_size(stat.st_size),
                "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "modified_time_formatted": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
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
        Search reports by keyword
        
        Args:
            keyword: Search keyword
            
        Returns:
            List of matching report info dicts
        """
        results = []
        keyword_lower = keyword.lower()
        
        for report_type in self.get_report_types():
            reports = self.get_reports_by_type(report_type["code"])
            for report in reports:
                if keyword_lower in report["name"].lower():
                    results.append(report)
        
        return results
