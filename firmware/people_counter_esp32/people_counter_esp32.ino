// People Counter - ESP32 outputs: 3 LEDs + relay
//
// The ESP32 makes no decisions: the PC app says which outputs are on, over USB serial
// (115200 baud), one line per update:
//   S<led1><led2><led3><relay>     e.g. "S1000" = LED1 on;  "S1111" = all LEDs + relay on
// The app's rules:
//   1 person   -> LED1
//   2 people   -> LED1 + LED2
//   3 or more  -> LED1 + LED2 + LED3 + relay
// If nothing arrives for WATCHDOG_MS (app closed, cable unplugged), everything turns off.
// You can also type "S1111" in the Arduino Serial Monitor to test the hardware without the app.
//
// Board: any ESP32 dev board (e.g. ESP32-WROOM-32 DevKit).
// Wiring: see ../../docs/wiring.svg

const int OUT_PINS[4] = {
  27,  // LED1 (1 person)   -> 220 ohm resistor -> LED -> GND
  26,  // LED2 (2 people)   -> 220 ohm resistor -> LED -> GND
  25,  // LED3 (3+ people)  -> 220 ohm resistor -> LED -> GND
  18,  // relay module IN (3+ people)
};
const int RELAY = 3;

// Most cheap blue relay modules switch ON when IN is pulled LOW. If yours clicks the
// wrong way round (on when it should be off), flip this.
const bool RELAY_ACTIVE_LOW = true;

const unsigned long WATCHDOG_MS = 3000;

bool state[4] = {false, false, false, false};
unsigned long lastMessageMs = 0;
String line;

void apply() {
  for (int i = 0; i < 4; i++) {
    bool level = state[i];
    if (i == RELAY && RELAY_ACTIVE_LOW) level = !level;
    digitalWrite(OUT_PINS[i], level ? HIGH : LOW);
  }
}

void handleLine(const String &cmd) {
  if (cmd.length() == 5 && (cmd[0] == 'S' || cmd[0] == 's')) {
    bool changed = false;
    for (int i = 0; i < 4; i++) {
      bool on = cmd[i + 1] == '1';
      changed |= on != state[i];
      state[i] = on;
    }
    if (changed) {
      Serial.printf("led1 %d, led2 %d, led3 %d, relay %d\n", state[0], state[1], state[2], state[3]);
    }
    lastMessageMs = millis();
    apply();
  } else if (cmd.length() > 0) {
    Serial.println("unknown command (use S<led1><led2><led3><relay>, e.g. S1111)");
  }
}

void setup() {
  Serial.begin(115200);
  for (int i = 0; i < 4; i++) pinMode(OUT_PINS[i], OUTPUT);
  apply();
  Serial.println("people_counter_esp32 ready");
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      line.trim();
      handleLine(line);
      line = "";
    } else if (line.length() < 32) {
      line += c;
    }
  }

  if (lastMessageMs && millis() - lastMessageMs > WATCHDOG_MS) {
    for (int i = 0; i < 4; i++) state[i] = false;
    lastMessageMs = 0;
    Serial.println("no data from app, all off");
    apply();
  }
}
