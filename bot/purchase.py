# -*- coding: utf-8 -*-
"""תפריט רכישת חבילות קופון — בחירה, אישור, הוראות תשלום בביט."""
from __future__ import annotations

from dataclasses import dataclass

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import BIT_PHONE, PAYMENT_CONFIRM_WHATSAPP_URL


@dataclass(frozen=True)
class PackageOption:
    package_id: str
    daily_quota: int
    period_days: int
    price_ils: int

    @property
    def tier(self) -> int:
        """מכסה יומית — תואמת ל-tier בקופון."""
        return self.daily_quota

    def label_hebrew(self) -> str:
        period = _period_label(self.period_days)
        return f"{self.daily_quota} תמונות ליום · {period} · ₪{self.price_ils}"

    def summary_hebrew(self) -> str:
        period = _period_label(self.period_days)
        return (
            f"• מכסה: *{self.daily_quota} תמונות ליום*\n"
            f"• תקופה: *{period}*\n"
            f"• מחיר: *₪{self.price_ils}*"
        )


def _period_label(days: int) -> str:
    if days == 30:
        return "חודש"
    if days == 90:
        return "3 חודשים"
    if days == 100:
        return "100 ימים"
    if days == 105:
        return "3.5 חודשים"
    return f"{days} ימים"


PACKAGE_CATALOG: tuple[PackageOption, ...] = (
    PackageOption("6_105", 6, 105, 150),
)

_PACKAGES_BY_ID: dict[str, PackageOption] = {p.package_id: p for p in PACKAGE_CATALOG}


def get_package(package_id: str) -> PackageOption | None:
    return _PACKAGES_BY_ID.get(package_id)


def purchase_menu_intro_hebrew() -> str:
    return (
        "*רכישת חבילה*\n\n"
        "בחר/י את החבילה המתאימה.\n"
        "אחרי אישור תקבל/י הוראות תשלום בביט — "
        "לאחר האישור שלנו יישלח אליך קוד קופון.\n\n"
        "כבר יש לך קוד? לחץ/י «יש לי קוד»."
    )


def build_purchase_menu_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for pkg in PACKAGE_CATALOG:
        rows.append(
            [
                InlineKeyboardButton(
                    pkg.label_hebrew(),
                    callback_data=f"buy:pkg:{pkg.package_id}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton("יש לי קוד", callback_data="buy:redeem")]
    )
    rows.append([InlineKeyboardButton("ביטול", callback_data="buy:cancel")])
    return InlineKeyboardMarkup(rows)


def build_package_confirm_keyboard(package_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "אישור והמשך לתשלום",
                    callback_data=f"buy:confirm:{package_id}",
                )
            ],
            [
                InlineKeyboardButton("חזרה", callback_data="buy:menu"),
                InlineKeyboardButton("ביטול", callback_data="buy:cancel"),
            ],
        ]
    )


def package_confirm_text_hebrew(pkg: PackageOption) -> str:
    return (
        "*סיכום החבילה*\n\n"
        f"{pkg.summary_hebrew()}\n\n"
        "לאשר ולקבל פרטי תשלום בביט?"
    )


def payment_instructions_hebrew(pkg: PackageOption) -> str:
    return (
        "*הבקשה נקלטה*\n\n"
        f"{pkg.summary_hebrew()}\n\n"
        "*לתשלום בביט:*\n"
        f"העבר/י *₪{pkg.price_ils}* לטלפון:\n"
        f"`{BIT_PHONE}`\n\n"
        "*אחרי התשלום:*\n"
        "שלח/י צילום מסך של אישור התשלום בוואטסאפ:\n"
        f"{PAYMENT_CONFIRM_WHATSAPP_URL}\n\n"
        "לאחר שנאשר את התשלום יישלח אליך קוד קופון בהודעה."
    )


def build_payment_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "שלח אישור תשלום בוואטסאפ",
                    url=PAYMENT_CONFIRM_WHATSAPP_URL,
                )
            ]
        ]
    )


def admin_purchase_notification_hebrew(
    *,
    user_id: int,
    username: str | None,
    first_name: str | None,
    pkg: PackageOption,
    request_id: int,
) -> str:
    uname = f"@{username}" if username else "—"
    name = first_name or "—"
    return (
        f"בקשת רכישה #{request_id}\n"
        f"משתמש: {name} ({uname})\n"
        f"user_id: {user_id}\n"
        f"חבילה: {pkg.label_hebrew()}\n"
        f"לגבות: ₪{pkg.price_ils} בביט"
    )


def parse_buy_callback(data: str) -> tuple[str, str] | None:
    """מחזיר (action, arg) עבור buy:action או buy:action:id."""
    if not data.startswith("buy:"):
        return None
    parts = data.split(":", 2)
    if len(parts) < 2:
        return None
    action = parts[1]
    arg = parts[2] if len(parts) > 2 else ""
    return action, arg
