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
    original_price_ils: int | None = None

    @property
    def tier(self) -> int:
        """מכסה יומית — תואמת ל-tier בקופון."""
        return self.daily_quota

    def label_hebrew(self) -> str:
        period = _period_label(self.period_days)
        if self.original_price_ils and self.original_price_ils != self.price_ils:
            return f"{period} · ₪{self.price_ils} (במקום ₪{self.original_price_ils})"
        return f"{period} · ₪{self.price_ils}"

    def summary_hebrew(self) -> str:
        period = _period_label(self.period_days)
        if self.original_price_ils and self.original_price_ils != self.price_ils:
            price_str = f"₪{self.price_ils} (במקום ₪{self.original_price_ils})"
        else:
            price_str = f"₪{self.price_ils}"
        return (
            f"• תקופה: <b>{period}</b>\n"
            f"• מחיר: <b>{price_str}</b>\n"
            f"• גישה מועדפת לפתרון ותרגול "
            f"(המתנה של 10 דקות בין שימושים)"
        )


def _period_label(days: int) -> str:
    if days == 30:
        return "חודש"
    if days == 60:
        return "חודשיים"
    if days == 90:
        return "3 חודשים"
    if days == 100:
        return "100 ימים"
    if days == 105:
        return "3.5 חודשים"
    if days == 120:
        return "4 חודשים"
    return f"{days} ימים"


PACKAGE_CATALOG: tuple[PackageOption, ...] = (
    PackageOption("6_30", 6, 30, 39),
    PackageOption("6_60", 6, 60, 74, 78),
    PackageOption("6_90", 6, 90, 105, 117),
    PackageOption("6_120", 6, 120, 134, 156),
)

_PACKAGES_BY_ID: dict[str, PackageOption] = {p.package_id: p for p in PACKAGE_CATALOG}


def get_package(package_id: str) -> PackageOption | None:
    return _PACKAGES_BY_ID.get(package_id)


def purchase_menu_intro_hebrew() -> str:
    return "כמה חודשים תרצה לקבל?"


def build_purchase_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            _period_label(pkg.period_days),
            callback_data=f"buy:pkg:{pkg.package_id}",
        )
        for pkg in PACKAGE_CATALOG
    ]
    return InlineKeyboardMarkup([buttons])


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
        "<b>סיכום החבילה</b>\n\n"
        f"{pkg.summary_hebrew()}\n\n"
        "לאשר ולקבל פרטי תשלום בביט?"
    )


def payment_instructions_hebrew(pkg: PackageOption) -> str:
    phone = BIT_PHONE.strip()
    return (
        f"{pkg.summary_hebrew()}\n\n"
        "<b>לתשלום בביט:</b>\n"
        f"העבר/י <b>₪{pkg.price_ils}</b> לטלפון:\n"
        f"<code>{phone}</code>\n\n"
        "<b>אחרי התשלום:</b>\n"
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
