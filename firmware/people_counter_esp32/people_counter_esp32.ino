// People Counter - ESP32 output: relay
//
// The ESP32 makes no decisions: the PC app says whether the relay is on, over USB serial
// (115200 baud), one line per update:
//   R1 = relay on (people count reached level 3 set in the app),  R0 = relay off
// The three level lamps are shown in the app's window, not on the ESP32.
// If nothing arrives for WATCHDOG_MS (app closed, cable unplugged), the relay turns off.
// You can also type "R1" in the Arduino Serial Monitor to test the hardware without the app.
//
// Board: any ESP32 dev board (e.g. ESP32-WROOM-32 DevKit).
// Wiring: see ../../docs/wiring.svg
//
// If it resets when the relay switches on, the relay coil is pulling the USB 5V down
// (brownout). The boot message below then says "brownout": power the relay module VCC
// from a separate 5V supply (GND shared with the ESP32) and/or put a 470uF capacitor
// across the relay VCC/GND.

#include <esp_system.h>

const int RELAY_PIN = 18;  // relay module IN

// Most cheap blue relay modules switch ON when IN is pulled LOW. If yours clicks the
// wrong way round (on when it should be off), flip this.
const bool RELAY_ACTIVE_LOW = true;

const unsigned long WATCHDOG_MS = 3000;

bool relayOn = false;
unsigned long lastMessageMs = 0;
String line;

void apply() {
  digitalWrite(RELAY_PIN, relayOn != RELAY_ACTIVE_LOW ? HIGH : LOW);
}

void handleLine(const String &cmd) {
  if (cmd.length() == 2 && (cmd[0] == 'R' || cmd[0] == 'r')) {
    bool on = cmd[1] == '1';
    if (on != relayOn) Serial.printf("relay %d\n", on);
    relayOn = on;
    lastMessageMs = millis();
    apply();
  } else if (cmd.length() > 0) {
    Serial.println("unknown command (use R1 or R0)");
  }
}

void setup() {
  Serial.begin(115200);
  apply();  // set the OFF level before the pin becomes an output, so the relay doesn't click at boot
  pinMode(RELAY_PIN, OUTPUT);
  apply();
  esp_reset_reason_t reason = esp_reset_reason();
  Serial.printf("people_counter_esp32 ready (reset reason %d%s)\n", reason,
                reason == ESP_RST_BROWNOUT ? ": brownout, see power note at the top of the code" : "");
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
    relayOn = false;
    lastMessageMs = 0;
    Serial.println("no data from app, relay off");
    apply();
  }
}
