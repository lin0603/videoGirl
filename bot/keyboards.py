from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def nsfw_opt_in_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ 我已成年，開啟 NSFW", callback_data="nsfw_yes"),
            ],
            [
                InlineKeyboardButton(text="❌ 保持 SFW", callback_data="nsfw_no"),
            ],
        ]
    )
