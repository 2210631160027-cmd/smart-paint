import json, os, datetime
from PIL import Image

def save_history(image_path, color, ratio, capacity):
    os.makedirs("static/history", exist_ok=True)

    img = Image.open(image_path)
    image_name = f"detected_{int(datetime.datetime.now().timestamp())}.jpg"
    save_path = f"static/history/{image_name}"
    img.save(save_path)

    data_file = "static/history/data.json"

    new_record = {
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "image": image_name,
        "color": color,
        "ratio": ratio,
        "capacity": capacity
    }

    if os.path.exists(data_file):
        with open(data_file, "r") as f:
            records = json.load(f)
    else:
        records = []

    records.append(new_record)

    with open(data_file, "w") as f:
        json.dump(records, f, indent=4)
