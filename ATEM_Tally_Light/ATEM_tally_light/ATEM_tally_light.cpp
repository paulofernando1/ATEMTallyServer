/*
    Copyright (C) 2023 Aron N. Het Lam, aronhetlam@gmail.com

    --- PROJECT ENHANCEMENTS & STABILITY FIXES (2024-2026) ---
    - INDEXING FIX: Corrected 1-indexing vs 0-indexing for Tally Flags.
    - PROTOCOL ALIGNMENT: Implemented 4-byte padding for TlIn commands from Server.
    - LED 2 BLINK: Implemented 500ms blink synchronization for the RGB LED.
    - OLED RECOVERY: Restored u8g2.begin() for stable I2C initialization.
    - REMOTE DISPLAY: Added 'Yellow Title' + 'Blue Message' layout.
    - AUTO-SCROLL: Implemented 30fps smooth horizontal scrolling for long messages.
    - DIAGNOSTICS: Cleaned up serial logs for optimized performance.
    ----------------------------------------------------------

    This program makes an ESP8266 into a wireless tally light system for ATEM switchers,
    by using Kasper Skårhøj's (<https://skaarhoj.com>) ATEM client libraries for Arduino.

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.
*/

#include "ATEM_tally_light.hpp"

#ifndef VERSION
#define VERSION "V 2.0"
#endif

// #define DEBUG_LED_STRIP
#define FASTLED_ALLOW_INTERRUPTS 0

#ifndef CHIP_FAMILY
#define CHIP_FAMILY "Unknown"
#endif

#ifndef VERSION
#define VERSION "Unknown"
#endif

#ifdef TALLY_TEST_SERVER
#define DISPLAY_NAME "Tally Test server"
#else
#define DISPLAY_NAME "Tally Light"
#endif

//Include libraries:
#ifdef ESP32
#include <esp_wifi.h>
#include <WebServer.h>
#include <WiFi.h>
#include <Update.h>
#else
#include <ESP8266WebServer.h>
#include <ESP8266WiFi.h>
#include <ESP8266HTTPUpdateServer.h>
#endif

#include <EEPROM.h>
#include <ATEMmin.h>
#include <TallyServer.h>
#include <FastLED.h>

//Include Display Libraries
//#include <Arduino.h>
#include <Wire.h>
#include <U8g2lib.h>

#ifdef ESP32
//Define LED1 color pins
#ifndef PIN_RED1
#define PIN_RED1 32
#endif
#ifndef PIN_GREEN1
#define PIN_GREEN1 33
#endif
#ifndef PIN_BLUE1
#define PIN_BLUE1 25
#endif

//Define LED2 color pins
#ifndef PIN_RED2
#define PIN_RED2 26
#endif
#ifndef PIN_GREEN2
#define PIN_GREEN2 27
#endif
#ifndef PIN_BLUE2
#define PIN_BLUE2 14
#endif


#else  // ESP8266
//Define LED1 color pins
#ifndef PIN_RED1
#define PIN_RED1 16  //D0 -- Default: 16 //D0
#endif
#ifndef PIN_GREEN1
#define PIN_GREEN1 5  //D1 -- Default: 4 // D2
#endif
#ifndef PIN_BLUE1
#define PIN_BLUE1 0  //D3 -- Default: 5 //D1
#endif

//Define LED2 color pins
#ifndef PIN_RED2
#define PIN_RED2 2  //D4 -- Default: 2 //D4
#endif
#ifndef PIN_GREEN2
#define PIN_GREEN2 13  //D7 -- Default: 14 //D5
#endif
#ifndef PIN_BLUE2
#define PIN_BLUE2 15  //D8 -- Default: 12 //D6
#endif
#endif


//Define LED colors
#define LED_OFF 0
#define LED_RED 1
#define LED_GREEN 2
#define LED_BLUE 3
#define LED_YELLOW 4
#define LED_PINK 5
#define LED_WHITE 6
#define LED_ORANGE 7
#define LED_CYAN 8

//Map "old" LED colors to CRGB colors
CRGB color_led[9] = { CRGB::Black, CRGB::Red, CRGB::Lime, CRGB::Blue, CRGB::Yellow, CRGB::Fuchsia, CRGB::White, CRGB::Orange, CRGB::Cyan };

//Define states
#define STATE_STARTING 0
#define STATE_CONNECTING_TO_WIFI 1
#define STATE_CONNECTING_TO_SWITCHER 2
#define STATE_RUNNING 3

//Define modes of operation
#define MODE_NORMAL 1
#define MODE_PREVIEW_STAY_ON 2
#define MODE_PROGRAM_ONLY 3
#define MODE_ON_AIR 4
#define MODE_AUX 5

#define TALLY_FLAG_OFF 0
#define TALLY_FLAG_PROGRAM 1
#define TALLY_FLAG_PREVIEW 2
#define TALLY_FLAG_LED2_R 4
#define TALLY_FLAG_LED2_G 8
#define TALLY_FLAG_LED2_B 16
#define TALLY_FLAG_ATTENTION 32
#define TALLY_FLAG_FORCE_LED2_AUX 64

//Define Neopixel status-LED options
#define NEOPIXEL_STATUS_FIRST 1
#define NEOPIXEL_STATUS_LAST 2
#define NEOPIXEL_STATUS_NONE 3

//FastLED
#ifndef TALLY_DATA_PIN
#ifdef ESP32
#define TALLY_DATA_PIN 12  //12
#elif ARDUINO_ESP8266_NODEMCU
#define TALLY_DATA_PIN 7  // SD0
#else
#define TALLY_DATA_PIN 1  //TX --- Default: 13 //D7
#endif
#endif
int numTallyLEDs;
int numStatusLEDs;
CRGB *leds;
CRGB *tallyLEDs;
CRGB *statusLED;
bool neopixelsUpdated = false;

//Initialize global variables
#ifdef ESP32
WebServer server(80);
#else
ESP8266WebServer server(80);
#endif

#ifndef TALLY_TEST_SERVER
ATEMmin atemSwitcher;
#else
int tallyFlag = TALLY_FLAG_OFF;
#endif

TallyServer tallyServer;

ImprovWiFi improv(&Serial);

uint8_t state = STATE_STARTING;
#ifndef ESP32
ESP8266HTTPUpdateServer httpUpdater;
#endif

//Define struct for holding tally settings (mostly to simplify EEPROM read and write, in order to persist settings)
struct Settings {
  char tallyName[32] = "";
  uint8_t tallyNo;
  uint8_t tallyModeLED1;
  uint8_t tallyModeLED2;
  bool staticIP;
  IPAddress tallyIP;
  IPAddress tallySubnetMask;
  IPAddress tallyGateway;
  IPAddress switcherIP;
  uint16_t neopixelsAmount;
  uint8_t neopixelStatusLEDOption;
  uint8_t neopixelBrightness;
  uint8_t ledBrightness;
  uint8_t blinkTimeLED2; // Blink time in seconds (as per user request)
};

Settings settings;

bool firstRun = true;

int bytesAvailable = false;
uint8_t readByte;

//Commented out for users without batteries
long secLoop = 0;
int lowLedCount = 0;
bool lowLedOn = false;
double uBatt = 0;
char buffer[3];

void onImprovWiFiErrorCb(ImprovTypes::Error err) {
}

void onImprovWiFiConnectedCb(const char *ssid, const char *password) {
}

//Display I2C variables
#define OLED_SCL 12  // Pino D5 do NodeMCU/Wemos
#define OLED_SDA 14  // Pino D6 do NodeMCU/Wemos
U8G2_SSD1306_128X64_NONAME_F_SW_I2C u8g2(U8G2_R0, /* clock=*/OLED_SCL, /* data=*/OLED_SDA, /* reset=*/U8X8_PIN_NONE);
int telaAtiva = 0;
bool displayLigado = true;
int ultimaTelaRenderizada = -1;
char remoteMessage[25] = "";
uint8_t lastMsgLen = 0;
unsigned long lastRepeaterReportMillis = 0;
unsigned long lastDisplayUpdate = 0;
int lastTallyState = -1;
bool blinkState = true;
unsigned long lastBlinkMillis = 0;

// Variables for auto-scroll logic
int scrollX = 128;
unsigned long lastScrollMillis = 0;
int textWidth = 0;

// Prototypes matching .hpp signatures exactly
void atualizarInterface();
void changeState(uint8_t stateToChangeTo);
void setBothLEDs(uint8_t color);
void setLED1(uint8_t color);
void setLED2(uint8_t color);
void setLED(uint8_t color, int pinRed, int pinGreen, int pinBlue);
void analogWriteWrapper(uint8_t pin, uint8_t value);
void setSTRIP(uint8_t color);
void setStatusLED(uint8_t color);
int getTallyState(uint16_t tallyNo);
int getLedColor(int tallyMode, int tallyNo, bool isLED2);
int getLedColor(int tallyMode, int tallyNo);  // Wrapper for legacy calls
void handleSave();
void handlePreview();
void handleNotFound();
String getSSID();

//Perform initial setup on power on
void setup() {
  // --- Robust Serial Startup ---
  Serial.begin(115200);
  Serial.flush();
  //delay(500);
  while (Serial.available()) Serial.read();  // Clear junk
  for (int i = 0; i < 5; i++) Serial.println();
  Serial.println(F("########################################"));
  Serial.println(F("#     TALLY LIGHT SYSTEM BOOTING...    #"));
  Serial.println(F("########################################"));

  //Inicialização da biblioteca do display
  u8g2.begin();
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_doomalpha04_tr);
  u8g2.drawStr(0, 10, "Iniciando...");
  u8g2.drawStr(0, 30, "IP: 192.168.4.1");
  u8g2.sendBuffer();

  //Init pins for LED
  pinMode(PIN_RED1, OUTPUT);
  pinMode(PIN_GREEN1, OUTPUT);
  pinMode(PIN_BLUE1, OUTPUT);

  pinMode(PIN_RED2, OUTPUT);
  pinMode(PIN_GREEN2, OUTPUT);
  pinMode(PIN_BLUE2, OUTPUT);

  // Ensure all LED2 pins start in OFF state
  digitalWrite(PIN_RED2, 0);
  digitalWrite(PIN_GREEN2, 0);
  digitalWrite(PIN_BLUE2, 0);

  //Onboard LED
  //pinMode(LED_BUILTIN, OUTPUT);
  //digitalWrite(LED_BUILTIN, HIGH);

  setBothLEDs(LED_BLUE);
  //Setup current-measuring pin
  pinMode(A0, INPUT);

  //Start Serial Text
  //Serial.begin(115200);
  Serial.println("Serial started");

  //Read settings from EEPROM. WIFI settings are stored separately by the ESP
  EEPROM.begin(sizeof(settings));  //Needed on ESP8266 module, as EEPROM lib works a bit differently than on a regular Arduino
  EEPROM.get(0, settings);

  // Safety check for tally number (0-based, 0-40 matches Cam 1-41)
  if (settings.tallyNo > 40) {
    settings.tallyNo = 0;
  }
  Serial.print(F("Tally ID Configured: "));
  Serial.println(settings.tallyNo + 1);

  // Safety check for blink time
  if (settings.blinkTimeLED2 == 0 || settings.blinkTimeLED2 > 60) {
    settings.blinkTimeLED2 = 1;
  }
  //Ugly fix for IPAddress not loading correctly when read from EEPROM
  settings.tallyIP = IPAddress(settings.tallyIP[0], settings.tallyIP[1], settings.tallyIP[2], settings.tallyIP[3]);
  settings.tallySubnetMask = IPAddress(settings.tallySubnetMask[0], settings.tallySubnetMask[1], settings.tallySubnetMask[2], settings.tallySubnetMask[3]);
  settings.tallyGateway = IPAddress(settings.tallyGateway[0], settings.tallyGateway[1], settings.tallyGateway[2], settings.tallyGateway[3]);
  settings.switcherIP = IPAddress(settings.switcherIP[0], settings.switcherIP[1], settings.switcherIP[2], settings.switcherIP[3]);

  //Initialize LED strip
  if (0 < settings.neopixelsAmount && settings.neopixelsAmount <= 1000) {
    leds = new CRGB[settings.neopixelsAmount];
    FastLED.addLeds<NEOPIXEL, TALLY_DATA_PIN>(leds, settings.neopixelsAmount);

    if (settings.neopixelStatusLEDOption != NEOPIXEL_STATUS_NONE) {
      numStatusLEDs = 1;
      numTallyLEDs = settings.neopixelsAmount - numStatusLEDs;
      if (settings.neopixelStatusLEDOption == NEOPIXEL_STATUS_FIRST) {
        statusLED = leds;
        tallyLEDs = leds + numStatusLEDs;
      } else {  // if last or or other value
        statusLED = leds + numTallyLEDs;
        tallyLEDs = leds;
      }
    } else {
      numTallyLEDs = settings.neopixelsAmount;
      numStatusLEDs = 0;
      tallyLEDs = leds;
    }
  } else {
    settings.neopixelsAmount = 0;
    numTallyLEDs = 0;
    numStatusLEDs = 0;
  }

  FastLED.setBrightness(settings.neopixelBrightness);
  setSTRIP(LED_OFF);
  setStatusLED(LED_BLUE);
  FastLED.show();

  Serial.println(settings.tallyName);

  if (settings.staticIP && settings.tallyIP != IPAddress(255, 255, 255, 255)) {
    WiFi.config(settings.tallyIP, settings.tallyGateway, settings.tallySubnetMask);
  } else {
    settings.staticIP = false;
  }

  //Put WiFi into station mode and make it connect to saved network
  WiFi.mode(WIFI_STA);
#ifdef ESP32
  WiFi.setHostname(settings.tallyName);
#else
  WiFi.hostname(settings.tallyName);
#endif
  WiFi.setAutoReconnect(true);
  WiFi.begin();

  Serial.println("------------------------");
  Serial.println("Connecting to WiFi...");
  Serial.println("Network name (SSID): " + getSSID());

  // Initialize and begin HTTP server for handeling the web interface
  server.on("/", handleRoot);
  server.on("/save", handleSave);
  server.on("/preview", handlePreview);
#ifdef ESP32
  server.on("/update", HTTP_POST, []() {
    server.sendHeader("Connection", "close");
    server.send(200, "text/plain", (Update.hasError()) ? "FAIL" : "OK");
    ESP.restart();
  }, []() {
    HTTPUpload& upload = server.upload();
    if (upload.status == UPLOAD_FILE_START) {
      Serial.printf("Update: %s\n", upload.filename.c_str());
      if (!Update.begin(UPDATE_SIZE_UNKNOWN)) { //start with max available size
        Update.printError(Serial);
      }
    } else if (upload.status == UPLOAD_FILE_WRITE) {
      if (Update.write(upload.buf, upload.currentSize) != upload.currentSize) {
        Update.printError(Serial);
      }
    } else if (upload.status == UPLOAD_FILE_END) {
      if (Update.end(true)) { //true to set the size to the current progress
        Serial.printf("Update Success: %u\nRebooting...\n", upload.totalSize);
      } else {
        Update.printError(Serial);
      }
    }
  });
#else
  httpUpdater.setup(&server, "/update");
#endif
  server.onNotFound(handleNotFound);
  server.begin();

  tallyServer.begin();

  improv.setDeviceInfo(CHIP_FAMILY, DISPLAY_NAME, VERSION, "Tally Light", "");
  improv.onImprovError(onImprovWiFiErrorCb);
  improv.onImprovConnected(onImprovWiFiConnectedCb);

  //Wait for result from first attempt to connect - This makes sure it only activates the softAP if it was unable to connect,
  //and not just because it hasn't had the time to do so yet. It's blocking, so don't use it inside loop()
  unsigned long start = millis();
  while ((!WiFi.status() || WiFi.status() >= WL_DISCONNECTED) && (millis() - start) < 10000LU) {
    bytesAvailable = Serial.available();
    if (bytesAvailable > 0) {
      readByte = Serial.read();
      improv.handleByte(readByte);
    }
  }

  //Set state to connecting before entering loop
  changeState(STATE_CONNECTING_TO_WIFI);

#ifdef TALLY_TEST_SERVER
  tallyServer.setTallySources(40);
#endif
}

void loop() {

  //Display Code



  //End Display Code

  bytesAvailable = Serial.available();
  if (bytesAvailable > 0) {
    readByte = Serial.read();
    improv.handleByte(readByte);
  }

  switch (state) {
    case STATE_CONNECTING_TO_WIFI:
      if (WiFi.status() == WL_CONNECTED) {
        WiFi.mode(WIFI_STA);  // Disable softAP if connection is successful
        Serial.println("------------------------");
        Serial.println("Connected to WiFi:   " + getSSID());
        Serial.println("IP:                  " + WiFi.localIP().toString());
        Serial.println("Subnet Mask:         " + WiFi.subnetMask().toString());
        Serial.println("Gateway IP:          " + WiFi.gatewayIP().toString());
#ifdef TALLY_TEST_SERVER
        Serial.println("Press enter (\\r) to loop through tally states.");
        changeState(STATE_RUNNING);
#else
        changeState(STATE_CONNECTING_TO_SWITCHER);
#endif
      } else if (firstRun) {
        firstRun = false;
        Serial.println("Unable to connect. Serving \"Tally Light setup\" WiFi for configuration, while still trying to connect...");
        Serial.println("Default IP: 192.168.4.1");
        WiFi.softAP((String)DISPLAY_NAME + " setup");
        WiFi.mode(WIFI_AP_STA);  // Enable softAP to access web interface in case of no WiFi
        setBothLEDs(LED_WHITE);
        setStatusLED(LED_WHITE);
      }
      break;
#ifndef TALLY_TEST_SERVER
    case STATE_CONNECTING_TO_SWITCHER:
      // Initialize a connection to the switcher:
      if (firstRun) {
        atemSwitcher.setTallyID(settings.tallyNo);
        atemSwitcher.begin(settings.switcherIP);
        // atemSwitcher.serialOutput(0x80); // Enable debug logs from library
        Serial.println("------------------------");
        Serial.println("Connecting to switcher...");
        Serial.println((String) "Switcher IP:         " + settings.switcherIP[0] + "." + settings.switcherIP[1] + "." + settings.switcherIP[2] + "." + settings.switcherIP[3]);
        firstRun = false;
      }
      atemSwitcher.runLoop();
      if (atemSwitcher.isConnected()) {
        changeState(STATE_RUNNING);
        Serial.println("Connected to switcher");
      }
      break;
#endif

    case STATE_RUNNING:
#ifdef TALLY_TEST_SERVER
      if (bytesAvailable && readByte == '\r') {
        tallyFlag++;
        tallyFlag %= 4;

        switch (tallyFlag) {
          case TALLY_FLAG_OFF:
            Serial.println("OFF");
            break;
          case TALLY_FLAG_PROGRAM:
            Serial.println("Program");
            break;
          case TALLY_FLAG_PREVIEW:
            Serial.println("Preview");
            break;
          case TALLY_FLAG_PROGRAM | TALLY_FLAG_PREVIEW:
            Serial.println("Program and preview");
            break;
          default:
            Serial.println("Invalid tally state...");
            break;
        }
      }

#endif

      // --- REPEATER CLIENT REPORTING (High Reliability) ---
      // Every 5 seconds, if this unit is a repeater, it reports its connected sub-clients
      // back to the main server. We now include the Roles (Tally IDs) for each sub-client
      // so the server dashboard can accurately display status orbs for them.
      if (millis() - lastRepeaterReportMillis >= 5000) {
        lastRepeaterReportMillis = millis();
        int maxC = tallyServer.getMaxClients();
        IPAddress clients[5]; // Standard max capacity for repeater report buffer
        int8_t roles[5];      // Sub-client Tally IDs (Roles)
        uint8_t count = 0;
        for (int i = 0; i < maxC && count < 5; i++) {
          if (tallyServer.isClientConnected(i)) {
            clients[count] = tallyServer.getClientIP(i);
            roles[count] = tallyServer.getClientTallyID(i);
            count++;
          }
        }
        if (count > 0) {
          // Send expanded Clnt packet [IP:4, Role:1, PAD:3]
          atemSwitcher.sendRepeaterClients(clients, roles, count);
        }
      }

#ifndef TALLY_TEST_SERVER
      //Handle data exchange and connection to swithcher
      atemSwitcher.runLoop();

      int tallySources = atemSwitcher.getTallyByIndexSources();
      tallyServer.setTallySources(tallySources);
      for (int i = 0; i < tallySources; i++) {
        tallyServer.setTallyFlag(i, atemSwitcher.getTallyByIndexTallyFlags(i));
      }
#endif

      //Handle Tally Server
      tallyServer.runLoop();

      // --- BLINK LOGIC (Configurable Interval) ---
      unsigned long blinkInterval = (unsigned long)settings.blinkTimeLED2 * 1000;
      if (millis() - lastBlinkMillis >= blinkInterval) {
        blinkState = !blinkState;
        lastBlinkMillis = millis();
      }

      //Set LED and Neopixel colors accordingly
      // --- LED 1 ---
      int color1 = getLedColor(settings.tallyModeLED1, settings.tallyNo, false);
      setLED1(color1);
      setSTRIP(color1);

      // --- LED 2 ---
      int color2 = getLedColor(settings.tallyModeLED2, settings.tallyNo, true);
      setLED2(color2);

      // --- REMOTE DISPLAY & LOGGING ---
      // Re-mapped to support up to 41 tallys + 41 display modes + message buffer
      // Display Mode is at 41 + settings.tallyNo
      uint8_t newTela = atemSwitcher.getTallyByIndexTallyFlags(41 + settings.tallyNo);
      if (newTela != telaAtiva) {
        // Serial.print("DISPLAY MODE: ");
        // Serial.println(newTela);
        telaAtiva = newTela;
        ultimaTelaRenderizada = -1;  // Force immediate refresh
        scrollX = 128;               // Reset scroll position on mode change
      }

      // Read Remote Message (Index 82-105) and Length (Index 106)
      uint8_t msgLen = atemSwitcher.getTallyByIndexTallyFlags(106);
      if (msgLen > 0 && msgLen != lastMsgLen) {
        // Serial.print("MSG RECEIVED: ");
        for (int i = 0; i < 24; i++) {
          remoteMessage[i] = (char)atemSwitcher.getTallyByIndexTallyFlags(82 + i);
        }
        remoteMessage[24] = '\0';
        // Serial.println(remoteMessage);
        lastMsgLen = msgLen;
        ultimaTelaRenderizada = -1;  // Force immediate refresh
        scrollX = 128;               // Reset scroll position for new message
      }

      // --- LOOP STATUS LOGGING (Commented out as requested) ---
      /*
      static unsigned long lastStatusLog = 0;
      if (millis() - lastStatusLog > 2000) {
          lastStatusLog = millis();
          Serial.print(F("ST: ")); Serial.print(state);
          Serial.print(F(" | CONN: ")); Serial.print(atemSwitcher.isConnected());
          Serial.print(F(" | CAM: ")); Serial.print(settings.tallyNo);
          Serial.print(F(" | DISP: ")); Serial.println(telaAtiva);
      }
      */

      // Handle Display Control Logic
      // Regular modes refresh occasionally, but MESSAGE mode scrolls at 30fps
      if (telaAtiva != ultimaTelaRenderizada || (telaAtiva == 6 && millis() - lastScrollMillis > 35)) {
        atualizarInterface();
        ultimaTelaRenderizada = telaAtiva;
        lastDisplayUpdate = millis();
        if (telaAtiva == 6) lastScrollMillis = millis();
      } else if (millis() - lastDisplayUpdate > 5000) {
        // Periodic refresh to ensure display stays correct
        atualizarInterface();
        lastDisplayUpdate = millis();
      }

#ifndef TALLY_TEST_SERVER
      //Switch state if ATEM connection is lost...
      if (!atemSwitcher.isConnected()) {  // will return false if the connection was lost
        Serial.println("------------------------");
        Serial.println("Connection to Switcher lost...");
        changeState(STATE_CONNECTING_TO_SWITCHER);

        //Reset tally server's tally flags, so clients turn off their lights.
        tallyServer.resetTallyFlags();
      }
#endif

      //Commented out for userst without batteries - Also timer is not done properly
      //batteryLoop();
      break;
  }

  //Switch state if WiFi connection is lost...
  if (WiFi.status() != WL_CONNECTED && state != STATE_CONNECTING_TO_WIFI) {
    Serial.println("------------------------");
    Serial.println("WiFi connection lost...");
    changeState(STATE_CONNECTING_TO_WIFI);

#ifndef TALLY_TEST_SERVER
    //Force atem library to reset connection, in order for status to read correctly on website.
    atemSwitcher.begin(settings.switcherIP);
    atemSwitcher.connect();
#endif

    //Reset tally server's tally flags, They won't get the message, but it'll be reset for when the connectoin is back.
    tallyServer.resetTallyFlags();
  }

  //Show strip only on updates
  if (neopixelsUpdated) {
    FastLED.show();
#ifdef DEBUG_LED_STRIP
    Serial.println("Updated LEDs");
#endif
    neopixelsUpdated = false;
  }

  //Handle web interface
  server.handleClient();
}

//Handle the change of states in the program
void changeState(uint8_t stateToChangeTo) {
  firstRun = true;
  switch (stateToChangeTo) {
    case STATE_CONNECTING_TO_WIFI:
      state = STATE_CONNECTING_TO_WIFI;
      setBothLEDs(LED_BLUE);
      setStatusLED(LED_BLUE);
      setSTRIP(LED_OFF);
      break;
    case STATE_CONNECTING_TO_SWITCHER:
      state = STATE_CONNECTING_TO_SWITCHER;
      setBothLEDs(LED_PINK);
      setStatusLED(LED_PINK);
      setSTRIP(LED_OFF);
      break;
    case STATE_RUNNING:
      state = STATE_RUNNING;
      setBothLEDs(LED_GREEN);
      setStatusLED(LED_ORANGE);
      break;
  }
}

//Set the color of both LEDs
void setBothLEDs(uint8_t color) {
  setLED(color, PIN_RED1, PIN_GREEN1, PIN_BLUE1);
  setLED(color, PIN_RED2, PIN_GREEN2, PIN_BLUE2);
}

//Set the color of the 1st LED
void setLED1(uint8_t color) {
  setLED(color, PIN_RED1, PIN_GREEN1, PIN_BLUE1);
}

//Set the color of the 2nd LED
void setLED2(uint8_t color) {
  setLED(color, PIN_RED2, PIN_GREEN2, PIN_BLUE2);
}

//Set the color of a LED using the given pins
void setLED(uint8_t color, int pinRed, int pinGreen, int pinBlue) {
#ifdef ESP32
  switch (color) {
    case LED_OFF:
      digitalWrite(pinRed, 0);
      digitalWrite(pinGreen, 0);
      digitalWrite(pinBlue, 0);
      break;
    case LED_RED:
      digitalWrite(pinRed, 1);
      digitalWrite(pinGreen, 0);
      digitalWrite(pinBlue, 0);
      break;
    case LED_GREEN:
      digitalWrite(pinRed, 0);
      digitalWrite(pinGreen, 1);
      digitalWrite(pinBlue, 0);
      break;
    case LED_BLUE:
      digitalWrite(pinRed, 0);
      digitalWrite(pinGreen, 0);
      digitalWrite(pinBlue, 1);
      break;
    case LED_YELLOW:
      digitalWrite(pinRed, 1);
      digitalWrite(pinGreen, 1);
      digitalWrite(pinBlue, 0);
      break;
    case LED_PINK:
      digitalWrite(pinRed, 1);
      digitalWrite(pinGreen, 0);
      digitalWrite(pinBlue, 1);
      break;
    case LED_WHITE:
      digitalWrite(pinRed, 1);
      digitalWrite(pinGreen, 1);
      digitalWrite(pinBlue, 1);
      break;
    case LED_CYAN:
      digitalWrite(pinRed, 0);
      digitalWrite(pinGreen, 1);
      digitalWrite(pinBlue, 1);
      break;
  }
#else
  uint8_t ledBrightness = settings.ledBrightness;
  void (*writeFunc)(uint8_t, uint8_t);
  if (ledBrightness >= 0xff) {
    writeFunc = &digitalWrite;
    ledBrightness = 1;
  } else {
    writeFunc = &analogWriteWrapper;
  }

  switch (color) {
    case LED_OFF:
      digitalWrite(pinRed, 0);
      digitalWrite(pinGreen, 0);
      digitalWrite(pinBlue, 0);
      break;
    case LED_RED:
      writeFunc(pinRed, ledBrightness);
      digitalWrite(pinGreen, 0);
      digitalWrite(pinBlue, 0);
      break;
    case LED_GREEN:
      digitalWrite(pinRed, 0);
      writeFunc(pinGreen, ledBrightness);
      digitalWrite(pinBlue, 0);
      break;
    case LED_BLUE:
      digitalWrite(pinRed, 0);
      digitalWrite(pinGreen, 0);
      writeFunc(pinBlue, ledBrightness);
      break;
    case LED_YELLOW:
      writeFunc(pinRed, ledBrightness);
      writeFunc(pinGreen, ledBrightness);
      digitalWrite(pinBlue, 0);
      break;
    case LED_PINK:
      writeFunc(pinRed, ledBrightness);
      digitalWrite(pinGreen, 0);
      writeFunc(pinBlue, ledBrightness);
      break;
    case LED_WHITE:
      writeFunc(pinRed, ledBrightness);
      writeFunc(pinGreen, ledBrightness);
      writeFunc(pinBlue, ledBrightness);
      break;
    case LED_CYAN:
      digitalWrite(pinRed, 0);
      writeFunc(pinGreen, ledBrightness);
      writeFunc(pinBlue, ledBrightness);
      break;
  }
#endif
}

void analogWriteWrapper(uint8_t pin, uint8_t value) {
  analogWrite(pin, value);
}

//Set the color of the LED strip, except for the status LED
void setSTRIP(uint8_t color) {
  if (numTallyLEDs > 0 && tallyLEDs[0] != color_led[color]) {
    for (int i = 0; i < numTallyLEDs; i++) {
      tallyLEDs[i] = color_led[color];
    }
    neopixelsUpdated = true;
#ifdef DEBUG_LED_STRIP
    Serial.println("Tally:  ");
    printLeds();
#endif
  }
}

//Set the single status LED (last LED)
void setStatusLED(uint8_t color) {
  if (numStatusLEDs > 0 && statusLED[0] != color_led[color]) {
    for (int i = 0; i < numStatusLEDs; i++) {
      statusLED[i] = color_led[color];
      if (color == LED_ORANGE) {
        statusLED[i].fadeToBlackBy(230);
      } else {
        statusLED[i].fadeToBlackBy(0);
      }
    }
    neopixelsUpdated = true;
#ifdef DEBUG_LED_STRIP
    Serial.println("Status: ");
    printLeds();
#endif
  }
}

#ifdef DEBUG_LED_STRIP
void printLeds() {
  for (int i = 0; i < settings.neopixelsAmount; i++) {
    Serial.print(i);
    Serial.print(", RGB: ");
    Serial.print(leds[i].r);
    Serial.print(", ");
    Serial.print(leds[i].g);
    Serial.print(", ");
    Serial.println(leds[i].b);
  }
  Serial.println();
}
#endif

int getTallyState(uint16_t tallyNo) {
#ifndef TALLY_TEST_SERVER
  uint16_t index = tallyNo;                          // settings.tallyNo is already 0-indexed (0=Cam1)
  if (index >= atemSwitcher.getTallyByIndexSources()) {  //out of range
    return TALLY_FLAG_OFF;
  }
  return atemSwitcher.getTallyByIndexTallyFlags(index);
#else
  return tallyFlag;
#endif
}

int getLedColor(int tallyMode, int tallyNo, bool isLED2) {
  if (tallyMode == MODE_ON_AIR) {
#ifndef TALLY_TEST_SERVER
    if (atemSwitcher.getStreamStreaming()) {
      return LED_RED;
    }
#endif
    return LED_OFF;
  }

  int tallyState = getTallyState(tallyNo);

  // Protocol: LED 2 RGB Control via bits 2, 3, 4
  // If bit 6 (0x40) is set, force AUX mode (RGB Control) regardless of local settings
  // Only apply this if we are calculating color for LED 2
  if (isLED2 && (tallyMode == MODE_AUX || (tallyState & TALLY_FLAG_FORCE_LED2_AUX))) {
    bool r = tallyState & TALLY_FLAG_LED2_R;
    bool g = tallyState & TALLY_FLAG_LED2_G;
    bool b = tallyState & TALLY_FLAG_LED2_B;

    // Apply blink if color is active (at least one component is true)
    if (!blinkState && (r || g || b)) return LED_OFF;

    if (r && g && b) return LED_WHITE;
    if (r && g) return LED_YELLOW;
    if (r && b) return LED_PINK;
    if (g && b) return LED_CYAN;
    if (r) return LED_RED;
    if (g) return LED_GREEN;
    if (b) return LED_BLUE;
    return LED_OFF;
  }

  // Normalized modes: 1=Normal, 2=Preview stay on, 3=Program only, 4=On Air
  if (tallyMode == MODE_ON_AIR) return LED_BLUE;
  if (tallyMode == MODE_PROGRAM_ONLY) {
      if (tallyState & TALLY_FLAG_PROGRAM) return LED_RED;
      return LED_OFF;
  }

  if (tallyState & TALLY_FLAG_PROGRAM) {  //if tally live
    return LED_RED;
  } else if (tallyState & TALLY_FLAG_ATTENTION) {  //Attention/Blue
    return LED_BLUE;
  } else if ((tallyState & TALLY_FLAG_PREVIEW        //if tally preview
              || tallyMode == MODE_PREVIEW_STAY_ON)  //or preview stay on
             && tallyMode != MODE_PROGRAM_ONLY) {    //and not program only
    return LED_GREEN;
  } else {  //if tally is neither
    return LED_OFF;
  }
}

// Wrapper for legacy calls to satisfy the linker
int getLedColor(int tallyMode, int tallyNo) {
  return getLedColor(tallyMode, tallyNo, false);
}

//Serve setup web page to client, by sending HTML with the correct variables
void handleRoot() {
  char buffer[10];
  String html = "<!DOCTYPE html><html><head><meta charset=\"UTF-8\">";
  html += "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">";
  html += "<title>" + (String)DISPLAY_NAME + " Settings</title>";
  html += "<style>";
  html += "body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #0f172a; color: #f8fafc; margin: 0; padding: 20px; }";
  html += ".container { max-width: 600px; margin: 0 auto; background: #1e293b; padding: 30px; border-radius: 12px; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1); }";
  html += "h1 { color: #3b82f6; font-size: 24px; margin-bottom: 20px; border-bottom: 2px solid #334155; padding-bottom: 10px; }";
  html += "h2 { color: #60a5fa; font-size: 18px; margin-top: 25px; margin-bottom: 15px; }";
  html += ".grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; align-items: center; }";
  html += "label { color: #94a3b8; font-size: 14px; }";
  html += "input, select { background: #0f172a; border: 1px solid #334155; color: #f8fafc; padding: 8px 12px; border-radius: 6px; font-size: 14px; width: 90%; }";
  html += "input:focus { outline: none; border-color: #3b82f6; }";
  html += ".btn { background: #3b82f6; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-weight: 600; transition: background 0.2s; width: 100%; margin-top: 20px; }";
  html += ".btn:hover { background: #2563eb; }";
  html += ".btn-ota { background: #10b981; margin-top: 10px; }";
  html += ".btn-ota:hover { background: #059669; }";
  html += ".info-box { background: #334155; padding: 15px; border-radius: 8px; margin-bottom: 20px; font-size: 13px; }";
  html += ".status { display: inline-block; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }";
  html += ".status-on { background: #059669; color: #ecfdf5; }";
  html += ".status-off { background: #dc2626; color: #fef2f2; }";
  html += ".card { background: #1e293b; padding: 20px; border-radius: 8px; border: 1px solid #334155; margin-bottom: 20px; }";
  html += ".ota-form { border-top: 2px solid #334155; margin-top: 30px; padding-top: 20px; }";
  html += ".footer { margin-top: 30px; font-size: 11px; color: #64748b; text-align: center; }";
  html += ".footer a { color: #3b82f6; text-decoration: none; }";
  html += ".opt-normal { color: #f8fafc; }";
  html += ".opt-preview { color: #22c55e !important; }";
  html += ".opt-program { color: #ef4444 !important; }";
  html += ".opt-onair { color: #3b82f6 !important; font-weight: bold; }";
  
  html += "select option { background: #1e293b; }"; 
  
  html += "</style>";
  html += "<script>";
  html += "function previewMode(el) {";
  html += "  var led = el.name == 'tModeLED1' ? 1 : 2;";
  html += "  var val = el.value;";
  html += "  fetch('/preview?led=' + led + '&mode=' + val);";
  html += "}";
  html += "function updateStaticFields() {";
  html += "  var staticOn = document.getElementById('staticIP').value == 'true';";
  html += "  var fields = ['tIP1','tIP2','tIP3','tIP4','mask1','mask2','mask3','mask4','gate1','gate2','gate3','gate4'];";
  html += "  fields.forEach(function(f) {";
  html += "    var el = document.getElementsByName(f);";
  html += "    for(var i=0; i<el.length; i++) el[i].disabled = !staticOn;";
  html += "  });";
  html += "}";
  html += "window.onload = updateStaticFields;";
  html += "</script>";
  html += "</head><body>";
  html += "<div class=\"container\">";
  html += "<h1>" + (String)DISPLAY_NAME + " Setup</h1>";

  html += "<div class=\"info-box\">";
  html += "<div><strong>Device Name:</strong> " + (String)settings.tallyName + "</div>";
  html += "<div><strong>IP:</strong> " + WiFi.localIP().toString() + "</div>";
  html += "<div><strong>Subnet Mask:</strong> " + WiFi.subnetMask().toString() + "</div>";
  html += "<div><strong>Gateway:</strong> " + WiFi.gatewayIP().toString() + "</div>";
  html += "<div><strong>Signal:</strong> " + String(WiFi.RSSI()) + " dBm</div>";
  
  // Calculate battery voltage if hardware supports it (A0)
  float vBat = (float)analogRead(A0) / 1023.0f * 4.2f;
  html += "<div><strong>Battery Voltage:</strong> " + String(vBat) + " V</div>";
  html += "<div><strong>Static IP:</strong> " + (String)(settings.staticIP ? "True" : "False") + "</div>";
  html += "<div><strong>Firmware Version:</strong> " + (String)VERSION + "</div>";

#ifndef TALLY_TEST_SERVER
  html += "<div><strong>Status:</strong> <span class=\"status " + (String)(atemSwitcher.isConnected() ? "status-on\">Connected" : "status-off\">Disconnected") + "</span></div>";
#endif
  html += "</div>";

  html += "<form action=\"/save\" method=\"post\">";
  html += "<h2>General Settings</h2>";
  html += "<div class=\"grid\">";
  html += "<div><label>Tally Light Name:</label><input type=\"text\" name=\"tName\" value=\"" + (String)settings.tallyName + "\" required></div>";
  html += "<div><label>Tally Light ID (1-41):</label><input type=\"number\" min=\"1\" max=\"41\" name=\"tNo\" value=\"" + String(settings.tallyNo + 1) + "\" required></div>";
  html += "<div><label>LED Brightness (0-255):</label><input type=\"number\" min=\"0\" max=\"255\" name=\"ledBright\" value=\"" + String(settings.ledBrightness) + "\" required></div>";
  html += "<div><label>LED2 Blink Time (sec):</label><input type=\"number\" min=\"1\" max=\"60\" name=\"blinkT\" value=\"" + String(settings.blinkTimeLED2) + "\" required></div>";
  html += "</div>";

  html += "<div style=\"display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 20px;\">";
  
  html += "<div class=\"card\">";
  html += "<h2>LED Modes</h2>";
  html += "<label>LED 1 Mode:</label><select name=\"tModeLED1\" onchange=\"previewMode(this)\">";
  html += "<option value=\"1\"" + (String)(settings.tallyModeLED1 == 1 ? " selected" : "") + " class=\"opt-normal\">Normal</option>";
  html += "<option value=\"2\"" + (String)(settings.tallyModeLED1 == 2 ? " selected" : "") + " class=\"opt-preview\">Preview</option>";
  html += "<option value=\"3\"" + (String)(settings.tallyModeLED1 == 3 ? " selected" : "") + " class=\"opt-program\">Program</option>";
  html += "<option value=\"4\"" + (String)(settings.tallyModeLED1 == 4 ? " selected" : "") + " class=\"opt-onair\">On Air</option>";
  html += "</select>";
  html += "<label style=\"margin-top:10px; display:block;\">LED 2 Mode:</label><select name=\"tModeLED2\" onchange=\"previewMode(this)\">";
  html += "<option value=\"1\"" + (String)(settings.tallyModeLED2 == 1 ? " selected" : "") + " class=\"opt-normal\">Normal</option>";
  html += "<option value=\"2\"" + (String)(settings.tallyModeLED2 == 2 ? " selected" : "") + " class=\"opt-preview\">Preview</option>";
  html += "<option value=\"3\"" + (String)(settings.tallyModeLED2 == 3 ? " selected" : "") + " class=\"opt-program\">Program</option>";
  html += "<option value=\"4\"" + (String)(settings.tallyModeLED2 == 4 ? " selected" : "") + " class=\"opt-onair\">On Air</option>";
  html += "</select>";
  html += "</div>";

  html += "<div class=\"card\">";
  html += "<h2>Neopixels</h2>";
  html += "<label>Amount:</label><input type=\"number\" name=\"neoPxAmount\" value=\"" + String(settings.neopixelsAmount) + "\">";
  html += "<label style=\"margin-top:10px; display:block;\">Brightness (0-255):</label><input type=\"number\" name=\"neoPxBright\" value=\"" + String(settings.neopixelBrightness) + "\">";
  html += "<label style=\"margin-top:10px; display:block;\">Status LED:</label><select name=\"neoPxStatus\">";
  html += "<option value=\"1\"" + (String)(settings.neopixelStatusLEDOption == 1 ? " selected" : "") + ">First LED</option>";
  html += "<option value=\"2\"" + (String)(settings.neopixelStatusLEDOption == 2 ? " selected" : "") + ">Last LED</option>";
  html += "<option value=\"3\"" + (String)(settings.neopixelStatusLEDOption == 3 ? " selected" : "") + ">None</option>";
  html += "</select>";
  html += "</div>";

  html += "</div>";

  html += "<div style=\"display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 20px;\">";

  html += "<div class=\"card\">";
  html += "<h2>WiFi Config</h2>";
  html += "<label>SSID:</label><input type=\"text\" name=\"ssid\" value=\"" + getSSID() + "\">";
  html += "<label style=\"margin-top:10px; display:block;\">Password:</label><input type=\"password\" name=\"pwd\" placeholder=\"Keep current\">";
  html += "</div>";

  html += "<div class=\"card\">";
  html += "<h2>Network</h2>";
  html += "<label>Use Static IP:</label><select name=\"staticIP\" id=\"staticIP\" onchange=\"updateStaticFields()\">";
  html += "<option value=\"false\"" + (String)(!settings.staticIP ? " selected" : "") + ">DHCP</option>";
  html += "<option value=\"true\"" + (String)(settings.staticIP ? " selected" : "") + ">Static</option>";
  html += "</select>";
  html += "<label style=\"margin-top:10px; display:block;\">Switcher IP:</label><div style=\"display: flex; gap: 2px;\">";
  for(int i=0; i<4; i++) {
    html += "<input type=\"text\" style=\"width:22%; text-align:center; padding: 4px 2px;\" name=\"aIP" + String(i+1) + "\" value=\"" + String(settings.switcherIP[i]) + "\" required>";
  }
  html += "</div>";
  html += "</div>";

  html += "</div>";

  html += "<h2>Static IP Settings</h2>";
  html += "<div class=\"grid\">";
  html += "<div><label>Device IP:</label><div style=\"display: flex; gap: 2px;\">";
  for(int i=0; i<4; i++) html += "<input type=\"text\" style=\"width:22%; text-align:center;\" name=\"tIP" + String(i+1) + "\" value=\"" + String(settings.tallyIP[i]) + "\">";
  html += "</div></div>";
  html += "<div><label>Subnet Mask:</label><div style=\"display: flex; gap: 2px;\">";
  for(int i=0; i<4; i++) html += "<input type=\"text\" style=\"width:22%; text-align:center;\" name=\"mask" + String(i+1) + "\" value=\"" + String(settings.tallySubnetMask[i]) + "\">";
  html += "</div></div>";
  html += "<div><label>Gateway:</label><div style=\"display: flex; gap: 2px;\">";
  for(int i=0; i<4; i++) html += "<input type=\"text\" style=\"width:22%; text-align:center;\" name=\"gate" + String(i+1) + "\" value=\"" + String(settings.tallyGateway[i]) + "\">";
  html += "</div></div>";
  html += "</div>";

  html += "<button type=\"submit\" class=\"btn\">Save & Restart Device</button>";
  html += "</form>";

  html += "<div class=\"ota-form\">";
  html += "<h2>Firmware Update (OTA)</h2>";
  html += "<div class=\"info-box\" style=\"background: #450a0a; border: 1px solid #991b1b;\">Select the .bin file generated by Arduino IDE to update the tally light. Do not power off during update.</div>";
  html += "<form method=\"POST\" action=\"/update\" enctype=\"multipart/form-data\">";
  html += "<input type=\"file\" name=\"update\" style=\"width:100%; margin-bottom:10px;\">";
  html += "<button type=\"submit\" class=\"btn btn-ota\">Flash Firmware</button>";
  html += "</form>";
  html += "</div>";

  html += "<div class=\"footer\">";
  html += "<p>&copy; 2026 Paulo Fernando de M. E. - Premium Tally System</p>";
  html += "<p>Based on ATEM libraries by <a href=\"https://www.skaarhoj.com/\">SKAARHOJ</a></p>";
  html += "</div>";
  html += "</div></body></html>";
  server.send(200, "text/html", html);
}

//Save new settings from client in EEPROM and restart the ESP8266 module
void handleSave() {
  if (server.method() != HTTP_POST) {
    server.send(405, "text/html", "<!DOCTYPE html><html><head><meta charset=\"ASCII\"><meta name=\"viewport\"content=\"width=device-width, initial-scale=1.0\"><title>Tally Light setup</title></head><body style=\"font-family:Verdana;\"><table bgcolor=\"#777777\"border=\"0\"width=\"100%\"cellpadding=\"1\"style=\"color:#ffffff;font-size:.8em;\"><tr><td><h1>&nbsp;" + (String)DISPLAY_NAME + " setup</h1></td></tr></table><br>Request without posting settings not allowed</body></html>");
  } else {
    String ssid;
    String pwd;
    bool change = false;
    for (uint8_t i = 0; i < server.args(); i++) {
      change = true;
      String var = server.argName(i);
      String val = server.arg(i);

      if (var == "tName") {
        val.toCharArray(settings.tallyName, (uint8_t)32);
      } else if (var == "tModeLED1") {
        int m = val.toInt();
        if (m >= 1 && m <= 4) settings.tallyModeLED1 = (uint8_t)m;
        else settings.tallyModeLED1 = 1;
      } else if (var == "tModeLED2") {
        int m = val.toInt();
        if (m >= 1 && m <= 4) settings.tallyModeLED2 = (uint8_t)m;
        else settings.tallyModeLED2 = 1;
      } else if (var == "ledBright") {
        settings.ledBrightness = val.toInt();
      } else if (var == "neoPxAmount") {
        settings.neopixelsAmount = val.toInt();
      } else if (var == "neoPxStatus") {
        settings.neopixelStatusLEDOption = val.toInt();
      } else if (var == "neoPxBright") {
        settings.neopixelBrightness = val.toInt();
      } else if (var == "tNo") {
        settings.tallyNo = val.toInt() - 1;
      } else if (var == "ssid") {
        ssid = String(val);
      } else if (var == "pwd") {
        pwd = String(val);
      } else if (var == "staticIP") {
        settings.staticIP = (val == "true");
      } else if (var == "tIP1") {
        settings.tallyIP[0] = val.toInt();
      } else if (var == "tIP2") {
        settings.tallyIP[1] = val.toInt();
      } else if (var == "tIP3") {
        settings.tallyIP[2] = val.toInt();
      } else if (var == "tIP4") {
        settings.tallyIP[3] = val.toInt();
      } else if (var == "mask1") {
        settings.tallySubnetMask[0] = val.toInt();
      } else if (var == "mask2") {
        settings.tallySubnetMask[1] = val.toInt();
      } else if (var == "mask3") {
        settings.tallySubnetMask[2] = val.toInt();
      } else if (var == "mask4") {
        settings.tallySubnetMask[3] = val.toInt();
      } else if (var == "gate1") {
        settings.tallyGateway[0] = val.toInt();
      } else if (var == "gate2") {
        settings.tallyGateway[1] = val.toInt();
      } else if (var == "gate3") {
        settings.tallyGateway[2] = val.toInt();
      } else if (var == "gate4") {
        settings.tallyGateway[3] = val.toInt();
      } else if (var == "aIP1") {
        settings.switcherIP[0] = val.toInt();
      } else if (var == "aIP2") {
        settings.switcherIP[1] = val.toInt();
      } else if (var == "aIP3") {
        settings.switcherIP[2] = val.toInt();
      } else if (var == "aIP4") {
        settings.switcherIP[3] = val.toInt();
      } else if (var == "blinkT") {
        settings.blinkTimeLED2 = val.toInt();
      }
    }

    if (change) {
      EEPROM.put(0, settings);
      EEPROM.commit();

      String html = "<!DOCTYPE html><html><head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">";
      html += "<title>Settings Saved</title><style>";
      html += "body { font-family: 'Segoe UI', sans-serif; background-color: #0f172a; color: white; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }";
      html += ".card { background: #1e293b; padding: 40px; border-radius: 12px; text-align: center; box-shadow: 0 10px 15px rgba(0,0,0,0.3); max-width: 400px; }";
      html += "h1 { color: #10b981; margin-bottom: 20px; }";
      html += ".btn { display: inline-block; background: #3b82f6; color: white; text-decoration: none; padding: 12px 24px; border-radius: 6px; font-weight: 600; margin-top: 25px; transition: background 0.2s; }";
      html += ".btn:hover { background: #2563eb; }";
      html += "</style></head><body><div class=\"card\">";
      html += "<h1>✔️ Settings Saved!</h1>";
      html += "<p>The Tally Light is restarting to apply the new configuration. This may take a few seconds.</p>";
      html += "<a href=\"/\" class=\"btn\">Return to Home</a>";
      html += "</div></body></html>";
      server.send(200, "text/html", html);

      // Delay to let data be saved, and the response to be sent properly to the client
      server.close();  // Close server to flush and ensure the response gets to the client
      delay(100);

      // Change into STA mode to disable softAP
      WiFi.mode(WIFI_STA);
      delay(100);  // Give it time to switch over to STA mode

      // Only re-configure WiFi if a new SSID was explicitly provided
      if (ssid.length() > 0) {
          // If the SSID is the same and we have no new password, don't trigger WiFi.begin()
          // which can clear the saved password in some SDK versions.
          if (WiFi.SSID() != ssid || pwd.length() > 0) {
              WiFi.persistent(true);
              if (pwd.length() > 0) {
                  WiFi.begin(ssid.c_str(), pwd.c_str());
              } else {
                  WiFi.begin(ssid.c_str()); 
              }
          }
      }

      //Delay to apply settings before restart
      delay(100);
      ESP.restart();
    }
  }
}

void handlePreview() {
  if (server.hasArg("led") && server.hasArg("mode")) {
    int led = server.arg("led").toInt();
    int mode = server.arg("mode").toInt();
    if (mode >= 1 && mode <= 4) {
      if (led == 1) settings.tallyModeLED1 = mode;
      else if (led == 2) settings.tallyModeLED2 = mode;
      Serial.println("Preview mode applied immediately.");
    }
  }
  server.send(200, "text/plain", "OK");
}

//Send 404 to client in case of invalid webpage being requested.
void handleNotFound() {
  server.send(404, "text/html", "<!DOCTYPE html><html><head><meta charset=\"ASCII\"><meta name=\"viewport\"content=\"width=device-width, initial-scale=1.0\"><title>" + (String)DISPLAY_NAME + " setup</title></head><body style=\"font-family:Verdana;\"><table bgcolor=\"#777777\"border=\"0\"width=\"100%\"cellpadding=\"1\"style=\"color:#ffffff;font-size:.8em;\"><tr><td><h1>&nbsp Tally Light setup</h1></td></tr></table><br>404 - Page not found</body></html>");
}

String getSSID() {
#ifdef ESP32
  wifi_config_t conf;
  esp_wifi_get_config(WIFI_IF_STA, &conf);
  return String(reinterpret_cast<const char *>(conf.sta.ssid));
#else
  return WiFi.SSID();
#endif
}


// Helper to draw the header (Yellow section on many OLEDs)
void desenharCabecalho(const char *titulo) {
  u8g2.setFont(u8g2_font_doomalpha04_tr);
  u8g2.drawStr(0, 10, titulo);
  u8g2.drawHLine(0, 14, 128);  // Separator line
}

//Void's para controle e definição do display I2C
void atualizarInterface() {
  u8g2.clearBuffer();

  // Se estiver em modo OFF (ou display desligado)
  if (telaAtiva == 0) {
    u8g2.sendBuffer();
    return;
  }

  u8g2.setFont(u8g2_font_doomalpha04_tr);

  switch (telaAtiva) {
    case 1:  // ON / Generic
      desenharCabecalho("STATUS: ON");
      u8g2.drawStr(0, 30, "TALLY PRO READY");
      u8g2.drawStr(0, 45, settings.tallyName);
      u8g2.drawStr(0, 60, "CAM ROLE ACTIVE");
      Serial.println("Remote Display: ON");
      break;
    case 2:  // Show IP
      desenharCabecalho("IP ADDRESS");
      u8g2.drawStr(0, 40, WiFi.localIP().toString().c_str());
      Serial.println("Remote Display: ShowIP");
      break;
    case 3:  // Tally Name
      desenharCabecalho("DEVICE NAME");
      u8g2.setFont(u8g2_font_callite24_tr);
      u8g2.drawStr(0, 40, settings.tallyName);
      Serial.println("Remote Display: Tally Name");
      break;
    case 4:  // WiFi Strength
      
      desenharCabecalho("WIFI SIGNAL");
      u8g2.drawStr(0, 40, (String(WiFi.RSSI()) + " dBm").c_str());
      if (WiFi.RSSI() > -50) {
        u8g2.drawStr(0, 60, ">->->->");
      } else if (WiFi.RSSI() > -60) {
        u8g2.drawStr(0, 60, ">->->");
      } else if (WiFi.RSSI() > -70) {
        u8g2.drawStr(0, 60, ">->");
      } else if (WiFi.RSSI() > -80) {
        u8g2.drawStr(0, 60, ">");
      } else {
        u8g2.drawStr(0, 60, "Weak Signal"); 
      }

      Serial.println("Remote Display: WIFI Signal");
      break;
    case 5:  // ALL
      desenharCabecalho("SYS INFO");
      u8g2.setFont(u8g2_font_scrum_tf);
      u8g2.drawStr(0, 25, (String("NAME: ") + settings.tallyName).c_str());
      u8g2.drawStr(0, 40, (String("IP:   ") + WiFi.localIP().toString()).c_str());
      u8g2.drawStr(0, 55, (String("RSSI: ") + WiFi.RSSI() + "dBm").c_str());
      //if (lastMsgLen > 0) u8g2.drawStr(0, 58, (String("> ") + remoteMessage).c_str());
      Serial.println("Remote Display: SYS Info");
      break;
    case 6:  // MESSAGE LARGE + SCROLL
      desenharCabecalho("REMOTE MESSAGE");
      Serial.println("Remote Display: Message Send");
      u8g2.setFont(u8g2_font_helvB10_tf);
      textWidth = u8g2.getStrWidth(remoteMessage);

      if (textWidth > 128) {
        // Scroll effect
        u8g2.drawStr(scrollX, 45, remoteMessage);
        scrollX -= 2;  // Speed
        if (scrollX < -textWidth) scrollX = 128;
      } else {
        // Static centered or left-aligned
        u8g2.drawStr(0, 45, remoteMessage);
      }
      break;
  }

  // Se houver uma mensagem remota e não for o modo "ALL" ou "MESSAGE", mostrar no rodapé
  //if (lastMsgLen > 0 && telaAtiva < 5 && telaAtiva != 0) {
  //  u8g2.setFont(u8g2_font_tom_thumb_4x6_tr);
  //u8g2.drawStr(0, 62, remoteMessage);
  //}
  u8g2.sendBuffer();
}

//Commented out for users without batteries - Also timer is not done properly
//Main loop for things that should work every second
// void batteryLoop() {
//     if (secLoop >= 400) {
//         //Get and calculate battery current
//         int raw = analogRead(A0);
//         uBatt = (double)raw / 1023 * 4.2;

//         //Set back status LED after one second to working LED_BLUE if it was changed by anything
//         if (lowLedOn) {
//             setStatusLED(LED_ORANGE);
//             lowLedOn = false;
//         }

//         //Blink every 5 seconds for one second if battery current is under 3.6V
//         if (lowLedCount >= 5 && uBatt <= 3.600) {
//             setStatusLED(LED_YELLOW);
//             lowLedOn = true;
//             lowLedCount = 0;
//         }
//         lowLedCount++;

//        //Turn stripes of and put ESP to deepsleep if battery is too low
//        if(uBatt <= 3.499) {
//            setSTRIP(LED_OFF);
//            setStatusLED(LED_OFF);
//            ESP.deepSleep(0, WAKE_NO_RFCAL);
//        }

//         secLoop = 0;
//     }
//     secLoop++;
// }
