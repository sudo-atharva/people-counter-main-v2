from app import esp32_message, lamps_on

assert esp32_message(0, (1, 2, 3)) == "R0"  # nobody: relay off
assert esp32_message(2, (1, 2, 3)) == "R0"
assert esp32_message(3, (1, 2, 3)) == "R1"  # level 3 reached: relay on
assert esp32_message(9, (2, 5, 10)) == "R0"  # levels set in the GUI
assert esp32_message(10, (2, 5, 10)) == "R1"
assert lamps_on(0, (1, 2, 3)) == [False, False, False]
assert lamps_on(2, (1, 2, 3)) == [True, True, False]
assert lamps_on(7, (2, 5, 10)) == [True, True, False]
print("ok")
