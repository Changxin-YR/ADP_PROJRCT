from __future__ import annotations

import re

from werkzeug.security import check_password_hash, generate_password_hash

# 常见弱密码黑名单：即使满足长度与字母数字组合要求也必须拒绝。
COMMON_WEAK_PASSWORDS = {
    "123456", "1234567", "12345678", "123456789", "1234567890", "654321", "987654321",
    "password", "password1", "passw0rd", "p@ssw0rd", "letmein", "welcome", "welcome1",
    "iloveyou", "monkey", "dragon", "football", "sunshine", "admin123", "admin888",
    "admin8888", "abc123", "abc1234", "abc12345", "abc123456", "abcd1234", "a123456",
    "aa123456", "aaa111", "1111aaaa", "aaaa1111", "qwerty", "qwertyui", "qwerty123",
    "1q2w3e4r", "1q2w3e4r5t", "1qaz2wsx", "zaq12wsx", "q1w2e3r4", "qwer1234",
    "asdf1234", "1234qwer", "111111", "11111111", "000000", "00000000", "666666",
    "66666666", "88888888", "123123", "123321", "147258369", "159357", "520520",
    "woaini1314", "1314520", "20200101",
}

# 键盘相邻序列（含反序）：出现在密码中即判弱。
KEYBOARD_SEQUENCES = (
    "qwerty", "asdfgh", "zxcvbn", "poiuyt", "lkjhgf", "mnbvc",
    "qazwsx", "wsxedc", "edcrfv", "rfvtgb", "tgbnhy", "yhnujm",
    "1qaz", "2wsx", "3edc", "4rfv", "5tgb", "6yhn", "7ujm",
    "zaq1", "xsw2", "cde3", "vfr4", "bgt5", "nhy6", "mju7",
    "1q2w3e4r", "q1w2e3r4", "9o0p", "0p9o",
)


def weak_password_reason(password: str) -> str | None:
    """返回弱密码原因（黑名单 / 连续数字 / 重复字符 / 键盘序列），不是弱密码返回 None。"""
    normalized = (password or "").strip().lower()
    if normalized in COMMON_WEAK_PASSWORDS:
        return "属于常见弱密码"
    digits = re.findall(r"\d{4,}", normalized)
    for run in digits:
        values = [int(char) for char in run]
        if all(next_value - current == 1 for current, next_value in zip(values, values[1:])):
            return "包含连续递增数字"
        if all(next_value - current == -1 for current, next_value in zip(values, values[1:])):
            return "包含连续递减数字"
    if re.search(r"(.)\1{3,}", normalized):
        return "包含连续重复字符"
    if any(sequence in normalized for sequence in KEYBOARD_SEQUENCES):
        return "包含键盘顺序字符"
    return None


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("密码不能为空")
    return generate_password_hash(password, method="scrypt")


def verify_password(password_hash: str, password: str) -> bool:
    if not password_hash or not password:
        return False
    return check_password_hash(password_hash, password)
