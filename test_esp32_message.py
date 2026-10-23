from app import esp32_message

assert esp32_message(0) == "S0000"  # nobody: all off
assert esp32_message(1) == "S1000"  # 1 person: LED1 (GPIO27)
assert esp32_message(2) == "S1100"  # 2 people: + LED2 (GPIO26)
assert esp32_message(3) == "S1111"  # 3 people: + LED3 (GPIO25) + relay (GPIO18)
assert esp32_message(9) == "S1111"
print("ok")
