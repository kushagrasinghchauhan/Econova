from pathlib import Path
import shutil

SRC = Path("training/dataset")
DST = SRC / "econova_3class"

# Source classes:
# 0 = plastic
# 1 = paper
# 2 = cardboard
# 3 = metal
# 4 = glass
# 5 = organic

# New classes:
# 0 = Organic
# 1 = Plastic
# 2 = Metal

CLASS_MAP = {
    5: 0,  # organic -> Organic
    0: 1,  # plastic -> Plastic
    3: 2,  # metal -> Metal
}

KEEP_CLASSES = set(CLASS_MAP.keys())

for split in ["train", "val"]:
    image_dir = DST / "images" / split
    label_dir = DST / "labels" / split

    image_dir.mkdir(parents=True, exist_ok=True)
    label_dir.mkdir(parents=True, exist_ok=True)

    source_images = SRC / "images" / split
    source_labels = SRC / "labels" / split

    count = 0

    for image in source_images.glob("*"):
        if not image.is_file():
            continue

        label_file = source_labels / f"{image.stem}.txt"

        if not label_file.exists():
            continue

        new_labels = []

        for line in label_file.read_text().splitlines():
            parts = line.split()

            if not parts:
                continue

            old_class = int(parts[0])

            if old_class not in KEEP_CLASSES:
                continue

            new_class = CLASS_MAP[old_class]
            new_labels.append(
                " ".join([str(new_class)] + parts[1:])
            )

        # Skip images that contain none of our 3 classes
        if not new_labels:
            continue

        shutil.copy2(
            image,
            image_dir / image.name
        )

        (label_dir / label_file.name).write_text(
            "\n".join(new_labels) + "\n"
        )

        count += 1

    print(f"{split}: {count} images converted")


yaml = """path: .
train: images/train
val: images/val

names:
  0: Organic
  1: Plastic
  2: Metal
"""

(DST / "dataset.yaml").write_text(yaml)

print()
print("===================================")
print("3-CLASS DATASET CREATED SUCCESSFULLY")
print("===================================")
print(f"Location: {DST.resolve()}")
print()
print("Classes:")
print("0 = Organic")
print("1 = Plastic")
print("2 = Metal")