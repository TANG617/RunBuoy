import time

from runbuoy import progress

for index in range(1, 11):
    progress(index, 10, unit="items", phase="processing", message=f"Item {index}")
    time.sleep(0.1)
