import cv2
import numpy as np

img = cv2.imread("debug_dealer_seat_3.png")
# O botao esta localizado no crop de dealer_seat_3
# Vamos extrair a regiao y: 18 a 34, x: 18 a 34 (16x16 pixels ou similar)
# De acordo com o grid impresso, os valores brilhantes (>100) estao entre y=20 e y=31, x=19 e x=32
# Vamos pegar y=18 a y=33 (altura 15), x=18 a x=33 (largura 15)
template = img[17:33, 17:33]
cv2.imwrite("vision/dealer_template.png", template)
print("Template do Dealer extraido e salvo em vision/dealer_template.png")
print("Dimensoes do template:", template.shape)
