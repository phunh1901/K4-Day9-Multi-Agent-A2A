"""
create_sample_inputs.py
Tạo 50 file sample input trong input/EC_001.json -> EC_050.json
dựa trên dữ liệu thực tế từ olist_orders_dataset.csv để test pipeline.
"""
from __future__ import annotations

import json
from pathlib import Path
import pandas as pd

ROOT_DIR = Path(__file__).parent
DATA_DIR = ROOT_DIR / "data"
INPUT_DIR = ROOT_DIR / "input"


def generate_sample_inputs():
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    df_orders = pd.read_csv(DATA_DIR / "olist_orders_dataset.csv", dtype=str)

    # Chọn 50 orders đa dạng (canceled, unavailable, delivered late, delivered on-time...)
    canceled = df_orders[df_orders["order_status"] == "canceled"]["order_id"].tolist()
    unavailable = df_orders[df_orders["order_status"] == "unavailable"]["order_id"].tolist()

    # Late delivery cases
    df_orders["delivered_dt"] = pd.to_datetime(df_orders["order_delivered_customer_date"], errors="coerce")
    df_orders["est_dt"] = pd.to_datetime(df_orders["order_estimated_delivery_date"], errors="coerce")
    late = df_orders[df_orders["delivered_dt"] > df_orders["est_dt"]]["order_id"].tolist()

    # Normal delivered cases
    normal = df_orders[df_orders["delivered_dt"] <= df_orders["est_dt"]]["order_id"].tolist()

    selected_orders = []
    # Pick canceled (up to 5)
    selected_orders.extend(canceled[:5])
    # Pick unavailable (up to 5)
    selected_orders.extend(unavailable[:5])
    # Pick late (up to 15)
    selected_orders.extend(late[:15])
    # Pick normal (fill the rest up to 50)
    for oid in normal:
        if oid not in selected_orders:
            selected_orders.append(oid)
            if len(selected_orders) == 50:
                break

    # If still not 50, fill with all remaining
    if len(selected_orders) < 50:
        for oid in df_orders["order_id"]:
            if oid not in selected_orders:
                selected_orders.append(oid)
                if len(selected_orders) == 50:
                    break

    print(f"Generating 50 sample input JSONs in {INPUT_DIR}...")
    for idx, order_id in enumerate(selected_orders, 1):
        case_id = f"EC_{idx:03d}"
        case_data = {
            "case_id": case_id,
            "customer_request": {
                "language": "vi",
                "message": "Hãy điều tra khiếu nại, kiểm tra lịch sử khách hàng và đối soát toàn bộ order.",
                "claimed_order_id": order_id,
            },
            "investigation_scope": {
                "include_customer_history": True,
                "include_product_context": True,
            },
            "policy_version": "EC_POLICY_V2",
        }

        output_file = INPUT_DIR / f"{case_id}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(case_data, f, ensure_ascii=False, indent=2)

    print(f"Successfully generated 50 sample inputs ({selected_orders[0]} ... {selected_orders[-1]}).")


if __name__ == "__main__":
    generate_sample_inputs()
