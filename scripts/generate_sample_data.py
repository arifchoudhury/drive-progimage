"""Generate small sample images in sample_data/ for trying the upload endpoint by hand."""

from pathlib import Path

from PIL import Image, ImageDraw

OUT_DIR = Path(__file__).resolve().parent.parent / "sample_data"
SIZE = 256


def red_square() -> Image.Image:
    return Image.new("RGB", (SIZE, SIZE), (220, 30, 30))


def gradient() -> Image.Image:
    img = Image.new("RGB", (SIZE, SIZE))
    pixels = img.load()
    assert pixels is not None
    for x in range(SIZE):
        for y in range(SIZE):
            pixels[x, y] = (x, y, 255 - x)
    return img


def checkerboard() -> Image.Image:
    img = Image.new("RGB", (SIZE, SIZE), "white")
    draw = ImageDraw.Draw(img)
    cell = 32
    for row in range(SIZE // cell):
        for col in range(SIZE // cell):
            if (row + col) % 2 == 0:
                draw.rectangle((col * cell, row * cell, (col + 1) * cell - 1, (row + 1) * cell - 1), fill="black")
    return img


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    red_square().save(OUT_DIR / "red-square.png")
    gradient().save(OUT_DIR / "gradient.jpg", quality=85)
    checkerboard().save(OUT_DIR / "checkerboard.gif")
    (OUT_DIR / "not-an-image.txt").write_text("This is not an image; uploading it should return 422.\n")
    print(f"Wrote sample data to {OUT_DIR}")


if __name__ == "__main__":
    main()
