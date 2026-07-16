from secondbrain.bot.navigation import build_folders_keyboard


def test_folders_keyboard_hides_empty_inbox_counter() -> None:
    keyboard = build_folders_keyboard(inbox_count=0)

    assert keyboard.inline_keyboard[0][0].text == "Входящие"
    assert keyboard.inline_keyboard[0][0].callback_data == "inbox:page:0"
    assert keyboard.inline_keyboard[1][0].text == "Разобранные"
    assert keyboard.inline_keyboard[1][0].callback_data == "folders:processed"
    assert keyboard.inline_keyboard[2][0].text == "Поиск по тегам"
    assert keyboard.inline_keyboard[2][0].callback_data == "folders:tags"
    assert keyboard.inline_keyboard[3][0].text == "Назад"
    assert keyboard.inline_keyboard[3][0].callback_data == "main:open"


def test_folders_keyboard_shows_only_inbox_counter() -> None:
    keyboard = build_folders_keyboard(inbox_count=3)

    assert keyboard.inline_keyboard[0][0].text == "Входящие (3)"
    assert keyboard.inline_keyboard[1][0].text == "Разобранные"
    assert keyboard.inline_keyboard[2][0].text == "Поиск по тегам"
