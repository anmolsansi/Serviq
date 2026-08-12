from pathlib import Path

import cv2
from PIL import Image, ImageFilter

TARGET_SIZE = (3840, 2160)
MODEL_PATH = Path(".cache/EDSR_x4.pb")

ASSETS = {
    Path("docs/design/serviq-client-portal.webp"): Path("docs/design/serviq-client-portal-4k.png"),
    Path("docs/design/serviq-customer-experience.webp"): Path("docs/design/serviq-customer-experience-4k.png"),
    Path("docs/design/serviq-platform-operator.webp"): Path("docs/design/serviq-platform-operator-4k.png"),
}


def upscale_with_edsr(source: Path, destination: Path) -> None:
    image = cv2.imread(str(source), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"Unable to read {source}")

    sr = cv2.dnn_superres.DnnSuperResImpl_create()
    sr.readModel(str(MODEL_PATH))
    sr.setModel("edsr", 4)
    enhanced = sr.upsample(image)
    enhanced = cv2.resize(enhanced, TARGET_SIZE, interpolation=cv2.INTER_LANCZOS4)

    temp = destination.with_suffix(".tmp.png")
    cv2.imwrite(str(temp), enhanced, [cv2.IMWRITE_PNG_COMPRESSION, 3])

    with Image.open(temp) as rendered:
        rendered = rendered.convert("RGB")
        rendered = rendered.filter(ImageFilter.UnsharpMask(radius=0.8, percent=115, threshold=2))
        rendered.save(destination, "PNG", compress_level=6)
    temp.unlink(missing_ok=True)


def upscale_with_lanczos(source: Path, destination: Path) -> None:
    with Image.open(source) as image:
        image = image.convert("RGB")
        image = image.resize(TARGET_SIZE, Image.Resampling.LANCZOS)
        image = image.filter(ImageFilter.UnsharpMask(radius=0.9, percent=120, threshold=2))
        image.save(destination, "PNG", compress_level=6)


def main() -> None:
    missing = [str(source) for source in ASSETS if not source.exists()]
    if missing:
        raise FileNotFoundError(f"Missing design sources: {', '.join(missing)}")

    use_edsr = MODEL_PATH.exists() and hasattr(cv2, "dnn_superres")
    print(f"4K target: {TARGET_SIZE[0]}x{TARGET_SIZE[1]}")
    print(f"EDSR super-resolution enabled: {use_edsr}")

    for source, destination in ASSETS.items():
        destination.parent.mkdir(parents=True, exist_ok=True)
        print(f"Upscaling {source} -> {destination}")
        try:
            if use_edsr:
                upscale_with_edsr(source, destination)
            else:
                upscale_with_lanczos(source, destination)
        except Exception as exc:
            print(f"EDSR failed for {source}: {exc}. Falling back to Lanczos.")
            upscale_with_lanczos(source, destination)

        with Image.open(destination) as result:
            if result.size != TARGET_SIZE:
                raise RuntimeError(f"Unexpected output dimensions for {destination}: {result.size}")
            print(f"Verified {destination}: {result.size[0]}x{result.size[1]}")


if __name__ == "__main__":
    main()
