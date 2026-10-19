"""Генерирует тестовый файл bookings.csv (замените его реальной выгрузкой)."""
import random
from datetime import date, timedelta

import pandas as pd

random.seed(42)

PROPERTIES = [f"Apt-{i:03d}" for i in range(1, 41)]
CHANNELS = ["Airbnb", "Booking", "Direct", "VRBO"]

rows = []
today = date.today()
for i in range(1, 421):
    check_in = today - timedelta(days=random.randint(0, 20))
    nights = random.randint(2, 10)
    price_per_night = random.randint(70, 260)
    rows.append(
        {
            "booking_id": f"B{i:05d}",
            "property": random.choice(PROPERTIES),
            "channel": random.choices(CHANNELS, weights=[40, 35, 15, 10])[0],
            "check_in": check_in,
            "check_out": check_in + timedelta(days=nights),
            "revenue": nights * price_per_night,
            "status": random.choices(["confirmed", "cancelled"], weights=[88, 12])[0],
        }
    )

df = pd.DataFrame(rows)

# Намеренно портим данные, как это бывает в реальных выгрузках
df = pd.concat([df, df.iloc[[5, 17]]], ignore_index=True)  # дубликаты
df.loc[30, "revenue"] = None  # пропущена сумма
df.loc[44, "check_out"] = df.loc[44, "check_in"] - timedelta(days=1)  # выезд раньше заезда

df.to_csv("bookings.csv", index=False)
print(f"Создан bookings.csv, строк: {len(df)}")
