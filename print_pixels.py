import cv2
import numpy as np

img = cv2.imread("debug_dealer_seat_3.png")
if img is None:
    print("Image not found")
    sys.exit(0)

# Convert to grayscale
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

print("Grayscale grid of debug_dealer_seat_3.png:")
h, w = gray.shape
for y in range(h):
    row = "".join(f"{gray[y, x]:4d}" for x in range(w))
    print(row)
