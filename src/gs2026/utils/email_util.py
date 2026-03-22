"""
邮件工具模块

提供邮件发送相关的功能。
"""

import smtplib
from email.mime.text import MIMEText
from email.header import Header
from typing import Set, List, Dict, Optional
from dataclasses import dataclass

from loguru import logger


@dataclass
class EmailContact:
    """邮件联系人"""
    name: str
    email: str

    def __str__(self) -> str:
        return f"{self.name} <{self.email}>"


class EmailUtil:
    """
    邮件工具类

    提供邮件发送功能，支持纯文本和HTML格式。
    """

    def __init__(
        self,
        smtp_server: str = "smtp.163.com",
        port: int = 465,
        sender_email: str = "m17600700886@163.com",
        password: str = "CPPHA5yTAZQLDju5"
    ) -> None:
        """
        初始化邮件工具

        Args:
            smtp_server: SMTP服务器地址
            port: SSL端口
            sender_email: 发件邮箱
            password: 邮箱授权码
        """
        self.smtp_server: str = smtp_server
        self.port: int = port
        self.sender_email: str = sender_email
        self.password: str = password

    def get_email_list(self) -> Set[str]:
        """
        获取所有邮箱地址

        Returns:
            邮箱地址集合
        """
        data_list: List[Dict[str, str]] = [
            {"name": "zhangqiang", "email_id": "m17600700886@163.com"},
        ]
        email_dict: Dict[str, str] = {item["email_id"]: item["name"] for item in data_list}
        all_emails: Set[str] = set(email_dict.keys())
        return all_emails

    def email_send(
        self,
        receiver_email: str,
        subject: str,
        content: str
    ) -> bool:
        """
        发送纯文本邮件

        Args:
            receiver_email: 收件人邮箱
            subject: 邮件主题
            content: 邮件正文

        Returns:
            是否发送成功
        """
        message = MIMEText(content, 'plain', 'utf-8')
        message['From'] = Header(self.sender_email, 'utf-8')
        message['To'] = Header(receiver_email, 'utf-8')
        message['Subject'] = Header(subject, 'utf-8')

        server: Optional[smtplib.SMTP_SSL] = None
        try:
            server = smtplib.SMTP_SSL(self.smtp_server, self.port)
            server.login(self.sender_email, self.password)
            server.sendmail(self.sender_email, receiver_email, message.as_string())
            logger.info(f"{receiver_email} 邮件发送成功！")
            return True
        except smtplib.SMTPException as e:
            logger.error(f"邮件发送失败，错误信息: {str(e)}")
            return False
        finally:
            if server:
                server.quit()

    def email_send_html(
        self,
        receiver_email: str,
        subject: str,
        html_content: str
    ) -> bool:
        """
        发送HTML邮件

        Args:
            receiver_email: 收件人邮箱
            subject: 邮件主题
            html_content: HTML内容

        Returns:
            是否发送成功
        """
        message = MIMEText(html_content, 'html', 'utf-8')
        message['From'] = Header(self.sender_email, 'utf-8')
        message['To'] = Header(receiver_email, 'utf-8')
        message['Subject'] = Header(subject, 'utf-8')

        server: Optional[smtplib.SMTP_SSL] = None
        try:
            server = smtplib.SMTP_SSL(self.smtp_server, self.port)
            server.login(self.sender_email, self.password)
            server.sendmail(self.sender_email, receiver_email, message.as_string())
            logger.info(f"{receiver_email} 邮件发送成功！")
            return True
        except smtplib.SMTPException as e:
            logger.error(f"邮件发送失败，错误信息: {str(e)}")
            return False
        finally:
            if server:
                server.quit()

    def full_html_fun(self, title: str, content: str) -> str:
        """
        生成完整HTML邮件内容

        Args:
            title: 标题
            content: 内容

        Returns:
            完整HTML字符串
        """
        full_html: str = f"""<!DOCTYPE html>
<html>
<head>
    <style>
        .data-block {{
            margin-bottom: 15px;
            font-family: Arial, sans-serif;
            color: #333;
        }}
    </style>
</head>
<body>
    <h3 style="color: #2c3e50;">{title}</h3>
    <div class="data-block">
        {content}
    </div>
    <hr>
    <p>本邮件由系统自动发送，请勿直接回复</p>
</body>
</html>"""
        return full_html
