#!/usr/bin/env python3
"""Рисует значки приложения для Android.

Зачем скрипт, а не готовые картинки: адаптивную иконку (Android 8 и новее)
Android собирает сам из вектора `drawable/ic_launcher_foreground.xml` и цвета
фона. А телефонам постарше (у нас поддерживаются с 7.0) нужна обычная
картинка — её и рисует этот скрипт, в тех же цветах и с тем же рисунком.

Запуск: python3 tools/make_icons.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

BACKGROUND = (0x5A, 0x2A, 0x4F)
HEADER = (0xE0, 0x72, 0x5F)
PAGE = (0xFF, 0xFF, 0xFF)

# Плотности Android: сколько точек на дюйм и какой размер значка из этого
# следует (значок — 48 dp, значит 48 * плотность).
DENSITIES = {
    "mdpi": 48,
    "hdpi": 72,
    "xhdpi": 96,
    "xxhdpi": 144,
    "xxxhdpi": 192,
}

# Рисуем крупно и уменьшаем: у Pillow нет сглаживания краёв, а без него
# скруглённые углы и кружки выходят рваными.
SUPERSAMPLE = 8

RES = Path(__file__).resolve().parent.parent / "android/app/src/main/res"
WINDOWS_ICON = Path(__file__).resolve().parent.parent / "desktop/cyclease.ico"


def draw_icon(size: int) -> Image.Image:
    scale = size * SUPERSAMPLE
    image = Image.new("RGBA", (scale, scale), (0, 0, 0, 0))
    painter = ImageDraw.Draw(image)

    painter.rounded_rectangle(
        (0, 0, scale - 1, scale - 1), radius=scale * 0.18, fill=BACKGROUND
    )

    page_top, page_bottom = scale * 0.24, scale * 0.80
    header_bottom = scale * 0.40
    painter.rounded_rectangle(
        (scale * 0.20, page_top, scale * 0.80, page_bottom),
        radius=scale * 0.06,
        fill=PAGE,
    )
    painter.rounded_rectangle(
        (scale * 0.20, page_top, scale * 0.80, header_bottom),
        radius=scale * 0.06,
        corners=(True, True, False, False),
        fill=HEADER,
    )

    # Пружина: белые стойки над листом. Рисуются после листа, поэтому поверх
    # его верхнего края — как и в векторе.
    ring_width = scale * 0.05
    for x in (0.30, 0.66):
        painter.rounded_rectangle(
            (
                scale * x - ring_width / 2,
                scale * 0.14,
                scale * x + ring_width / 2,
                scale * 0.36,
            ),
            radius=ring_width / 2,
            fill=PAGE,
        )

    # Дни: две недели по три.
    dot = scale * 0.055
    for row, y in enumerate((0.53, 0.66)):
        for column, x in enumerate((0.32, 0.47, 0.62)):
            painter.ellipse(
                (scale * x, scale * y, scale * x + dot, scale * y + dot),
                fill=BACKGROUND,
            )

    return image.resize((size, size), Image.LANCZOS)


def main() -> None:
    for density, size in DENSITIES.items():
        folder = RES / f"mipmap-{density}"
        folder.mkdir(parents=True, exist_ok=True)
        icon = draw_icon(size)
        icon.save(folder / "ic_launcher.png")
        icon.save(folder / "ic_launcher_round.png")
        print(f"mipmap-{density}: ic_launcher.png, ic_launcher_round.png ({size}px)")

    # Значок для собранного exe: Windows ждёт файл .ico с картинками разного
    # размера внутри — из него берётся и значок программы в панели задач, и
    # маленький значок в списке файлов.
    layers = [draw_icon(size) for size in (16, 24, 32, 48, 64, 128, 256)]
    layers[-1].save(
        WINDOWS_ICON, format="ICO", sizes=[(image.width, image.height) for image in layers]
    )
    print(f"desktop/{WINDOWS_ICON.name}: значок для exe")


if __name__ == "__main__":
    main()
