/*
 * AllSkyHyde ESP32 Display Client
 * For JC3248W535C_I_Y (ESP32-S3 with 320x480 IPS Display)
 *
 * This sketch fetches the latest AllSky image from your Flask server
 * and displays it on the ESP32's built-in display with touch controls.
 *
 * Hardware: JC3248W535C_I_Y
 * - ESP32-S3-WROOM-1U-N16R8
 * - 3.5" IPS Display (320x480)
 * - AXS15231B Display Driver
 * - Touch controller (I2C)
 *
 * Required Libraries:
 * - U8g2lib (install via Library Manager) - MUST be included FIRST!
 * - Arduino_GFX (install via Library Manager)
 * - HTTPClient (built-in)
 * - WiFi (built-in)
 * - JPEGDEC (install via Library Manager)
 * - Wire (built-in)
 * - ArduinoJson (install via Library Manager)
 */

// IMPORTANT: U8g2lib must be included BEFORE Arduino_GFX_Library
#include <U8g2lib.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <FS.h>
#include <Arduino_GFX_Library.h>
#include <JPEGDEC.h>
#include <Wire.h>
#include <ArduinoJson.h>
#include "WeatherIcons.h"

// ========== CONFIGURATION ==========
// WiFi Configuration
const char* WIFI_SSID = "hyde-home";
const char* WIFI_PASSWORD = "H0bby1st(__)";

// AllSkyHyde Server Configuration
const char* ALLSKY_SERVER = "http://192.168.0.137:5000";  // Your kickpi server
const char* API_ENDPOINT = "/api/latest_image_preview";
const char* API_WEATHER_ENDPOINT = "/api/weather";

// Update interval (milliseconds)
const unsigned long UPDATE_INTERVAL = 300000;  // 300 seconds (5 minutes) - matches capture interval

// Touch Configuration (from working_example.ino)
#define TOUCH_ADDR 0x3B
#define TOUCH_SDA 4
#define TOUCH_SCL 8
#define TOUCH_I2C_CLOCK 400000
#define TOUCH_RST_PIN 12
#define TOUCH_INT_PIN 11
#define AXS_MAX_TOUCH_NUMBER 1

// ========== DISPLAY SETUP ==========
// Pin definitions for JC3248W535C (QSPI interface)
#define GFX_BL 1   // Backlight

// QSPI pins for JC3248W535C with ESP32-S3
// CS, SCK, MOSI, MISO, D2, D3
Arduino_DataBus *bus = new Arduino_ESP32QSPI(45, 47, 21, 48, 40, 39);

// AXS15231B driver for JC3248W535C
// EXACTLY matching working_example.ino
Arduino_GFX *g = new Arduino_AXS15231B(bus, GFX_NOT_DEFINED, 0, false, 320, 480);

// Canvas with rotation 0 (will rotate to landscape in setup)
Arduino_Canvas *gfx = new Arduino_Canvas(320, 480, g, 0, 0, 0);

// ========== GLOBAL OBJECTS ==========
JPEGDEC jpeg;
HTTPClient http;
WiFiClient client;

// ========== STATE VARIABLES ==========
unsigned long lastUpdateTime = 0;
String lastImageFilename = "";
bool isConnected = false;
int jpegCallbackCount = 0;
uint16_t touchX, touchY;
bool showingWeather = false;  // Track current view mode
unsigned long lastTouchTime = 0;  // For debouncing
bool touchProcessed = false;  // Prevent multiple triggers

// Weather data structure
struct WeatherData {
  String description;
  float temperature;
  int humidity;
  int pressure;
  int clouds;
  float rain;
  float windSpeed;
  String iconCode;
} currentWeather;

// ========== JPEG DECODER CALLBACK ==========
// This function is called by the JPEG decoder to draw decoded pixels
int jpegDrawCallback(JPEGDRAW *pDraw) {
  jpegCallbackCount++;

  // Debug first few callbacks
  if (jpegCallbackCount <= 3) {
    Serial.print("Callback #");
    Serial.print(jpegCallbackCount);
    Serial.print(": x=");
    Serial.print(pDraw->x);
    Serial.print(", y=");
    Serial.print(pDraw->y);
    Serial.print(", w=");
    Serial.print(pDraw->iWidth);
    Serial.print(", h=");
    Serial.print(pDraw->iHeight);

    // Print first few pixel values to debug
    Serial.print(", first pixels: ");
    for (int i = 0; i < 5 && i < pDraw->iWidth; i++) {
      Serial.print(pDraw->pPixels[i], HEX);
      Serial.print(" ");
    }
    Serial.println();
  }

  // Draw the JPEG to the canvas
  gfx->draw16bitRGBBitmap(pDraw->x, pDraw->y, pDraw->pPixels, pDraw->iWidth, pDraw->iHeight);

  return 1;  // Continue decoding
}

// ========== SETUP ==========
void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("AllSkyHyde ESP32 Display Client");
  Serial.println("================================");

  // Initialize Display
  Serial.println("Initializing display...");

  // Initialize backlight
  pinMode(GFX_BL, OUTPUT);
  digitalWrite(GFX_BL, HIGH);  // Turn on backlight
  Serial.println("Backlight ON");

  // Initialize display and canvas
  Serial.println("Calling gfx->begin()...");
  gfx->begin();
  Serial.println("Display begin() successful");

  Serial.print("Display dimensions: ");
  Serial.print(gfx->width());
  Serial.print(" x ");
  Serial.println(gfx->height());

  // Keep rotation 0 - server will rotate the image for us
  Serial.println("Using rotation 0, server-side rotation enabled");

  // Initialize touch
  Serial.println("Initializing touch...");
  Wire.begin(TOUCH_SDA, TOUCH_SCL);
  Wire.setClock(TOUCH_I2C_CLOCK);

  pinMode(TOUCH_INT_PIN, INPUT_PULLUP);
  pinMode(TOUCH_RST_PIN, OUTPUT);
  digitalWrite(TOUCH_RST_PIN, LOW);
  delay(200);
  digitalWrite(TOUCH_RST_PIN, HIGH);
  delay(200);
  Serial.println("Touch initialized");

  // Display startup message
  gfx->setRotation(1);  // Landscape
  gfx->fillScreen(BLACK);
  gfx->setTextColor(WHITE);
  gfx->setTextSize(3);
  gfx->setCursor(100, 120);
  gfx->println("AllSkyHyde");
  gfx->setTextSize(2);
  gfx->setCursor(150, 160);
  gfx->println("Starting...");
  gfx->flush();
  gfx->setRotation(0);  // Reset to portrait

  // Connect to WiFi
  Serial.print("Connecting to WiFi: ");
  Serial.println(WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    isConnected = true;
    Serial.println("\nWiFi connected!");
    Serial.print("IP address: ");
    Serial.println(WiFi.localIP());

    // Fetch first image immediately
    fetchAndDisplayImage();
  } else {
    Serial.println("\nWiFi connection failed!");
    gfx->setRotation(1);  // Landscape
    gfx->fillScreen(BLACK);
    gfx->setTextColor(RED);
    gfx->setTextSize(2);
    gfx->setCursor(140, 120);
    gfx->println("WiFi Failed!");
    gfx->setCursor(130, 160);
    gfx->println("Check config");
    gfx->flush();
    gfx->setRotation(0);  // Reset to portrait
  }
}

// ========== MAIN LOOP ==========
void loop() {
  // Check WiFi connection
  if (WiFi.status() != WL_CONNECTED) {
    if (isConnected) {
      Serial.println("WiFi connection lost! Reconnecting...");
      isConnected = false;
      displayError("WiFi Lost");
    }
    WiFi.reconnect();
    delay(5000);
    return;
  } else if (!isConnected) {
    isConnected = true;
    Serial.println("WiFi reconnected!");
  }

  // Check if it's time to update image (only when showing image view)
  unsigned long currentTime = millis();
  if (!showingWeather && (currentTime - lastUpdateTime >= UPDATE_INTERVAL || lastUpdateTime == 0)) {
    fetchAndDisplayImage();
    lastUpdateTime = currentTime;
  }

  // Check for touch events with proper debouncing
  unsigned long currentTouchTime = millis();
  bool touchDetected = getTouchPoint(touchX, touchY);

  // Debounce: ignore touches for 500ms after last touch
  if (touchDetected && !touchProcessed && (currentTouchTime - lastTouchTime > 500)) {
    Serial.print("Touch detected at: ");
    Serial.print(touchX);
    Serial.print(", ");
    Serial.println(touchY);

    touchProcessed = true;
    lastTouchTime = currentTouchTime;

    if (showingWeather) {
      // Weather display is in landscape (rotation 1)
      // Back button drawn at: X: 10-150, Y: 260-310 in landscape coordinates
      // Touch hardware returns portrait coordinates

      Serial.println("=== Weather view touch ===");

      // Back button area in portrait coordinates
      // Based on your debug: X: 92, Y: 308 should trigger back
      // Expanded hit area for easier touching
      if (touchX <= 150 && touchY >= 250) {
        Serial.println("=== BACK BUTTON PRESSED ===");
        showingWeather = false;

        // Wait for finger to be lifted before switching views
        delay(200);
        while(getTouchPoint(touchX, touchY)) {
          delay(50);  // Wait until touch is released
        }

        fetchAndDisplayImage();  // Redisplay the image
      } else {
        Serial.println("Touch outside back button area");
      }
    } else {
      // Touch anywhere on image view to show weather
      Serial.println("=== Switching to weather view ===");
      showingWeather = true;

      // Wait for finger to be lifted before switching views
      delay(200);
      while(getTouchPoint(touchX, touchY)) {
        delay(50);  // Wait until touch is released
      }

      fetchWeatherData();
      displayWeather();
    }

    // Reset processed flag after a delay
    delay(100);
  }

  // Reset touch processed flag when no touch detected
  if (!touchDetected) {
    touchProcessed = false;
  }

  delay(50);  // Small delay to prevent tight looping
}

// ========== FETCH AND DISPLAY IMAGE ==========
void fetchAndDisplayImage() {
  Serial.println("\n--- Fetching latest image ---");

  // Build URL
  String url = String(ALLSKY_SERVER) + String(API_ENDPOINT);

  // Request portrait image (320x480) that will fill the display
  // Server rotates the landscape source image 90 degrees to create this
  url += "?width=320&height=480&quality=85&rotate=90";

  Serial.print("URL: ");
  Serial.println(url);

  // Start HTTP connection with longer timeout
  http.begin(client, url);
  http.setTimeout(60000);  // 60 second timeout
  http.setReuse(false);  // Don't reuse connections

  Serial.println("Sending HTTP GET request...");

  // Send GET request
  int httpCode = http.GET();

  Serial.print("HTTP Response Code: ");
  Serial.println(httpCode);

  if (httpCode == HTTP_CODE_OK) {
    // Get response headers
    String filename = http.header("X-Image-Filename");
    String timestamp = http.header("X-Image-Timestamp");
    String exposure = http.header("X-Image-Exposure-Ms");

    Serial.println("Image metadata:");
    Serial.print("  Filename: ");
    Serial.println(filename);
    Serial.print("  Timestamp: ");
    Serial.println(timestamp);
    Serial.print("  Exposure: ");
    Serial.print(exposure);
    Serial.println(" ms");

    // Check if this is a new image
    if (filename == lastImageFilename && lastImageFilename != "") {
      Serial.println("Same image as before, skipping display update");
      http.end();
      return;
    }

    lastImageFilename = filename;

    // Get image data
    int contentLength = http.getSize();
    Serial.print("  Size: ");
    Serial.print(contentLength);
    Serial.println(" bytes");

    // Get the stream
    WiFiClient* stream = http.getStreamPtr();

    // Allocate buffer for JPEG data
    uint8_t* jpegBuffer = (uint8_t*)ps_malloc(contentLength);  // Use PSRAM

    if (jpegBuffer == NULL) {
      Serial.println("ERROR: Failed to allocate memory for JPEG!");
      displayError("Memory Error");
      http.end();
      return;
    }

    // Read image data into buffer
    int bytesRead = 0;
    unsigned long startTime = millis();

    while (http.connected() && bytesRead < contentLength) {
      size_t available = stream->available();
      if (available) {
        int readBytes = stream->readBytes(jpegBuffer + bytesRead, available);
        bytesRead += readBytes;

        // Show progress
        if (bytesRead % 10240 == 0) {  // Every 10KB
          Serial.print(".");
        }
      }
      delay(1);
    }

    unsigned long downloadTime = millis() - startTime;
    Serial.println();
    Serial.print("Downloaded ");
    Serial.print(bytesRead);
    Serial.print(" bytes in ");
    Serial.print(downloadTime);
    Serial.println(" ms");

    // Decode and display JPEG
    // Open RAM buffer with callback
    if (jpeg.openRAM(jpegBuffer, bytesRead, jpegDrawCallback)) {
      Serial.println("Decoding JPEG...");

      // Try setting pixel type - use LITTLE_ENDIAN for ESP32
      jpeg.setPixelType(RGB565_LITTLE_ENDIAN);

      // Get JPEG info
      int jpegWidth = jpeg.getWidth();
      int jpegHeight = jpeg.getHeight();
      Serial.print("JPEG dimensions: ");
      Serial.print(jpegWidth);
      Serial.print(" x ");
      Serial.println(jpegHeight);

      // Clear screen to BLACK
      Serial.println("Clearing screen to BLACK...");
      gfx->fillScreen(BLACK);
      gfx->flush();

      // Calculate scale to fit JPEG to canvas
      int canvasWidth = gfx->width();
      int canvasHeight = gfx->height();
      Serial.print("Canvas dimensions: ");
      Serial.print(canvasWidth);
      Serial.print(" x ");
      Serial.println(canvasHeight);

      // Scale to fit - use JPEG_SCALE_HALF, JPEG_SCALE_QUARTER, or JPEG_SCALE_EIGHTH if needed
      int scale = 0;  // 0 = 1:1, 1 = 1:2, 2 = 1:4, 3 = 1:8

      // Decode and display (callback will draw to canvas)
      Serial.println("Starting JPEG decode...");
      jpegCallbackCount = 0;  // Reset counter
      startTime = millis();
      int result = jpeg.decode(0, 0, scale);  // x, y, scale
      jpeg.close();

      unsigned long decodeTime = millis() - startTime;
      Serial.print("Decoded in ");
      Serial.print(decodeTime);
      Serial.print(" ms, result: ");
      Serial.print(result);
      Serial.print(", callback called ");
      Serial.print(jpegCallbackCount);
      Serial.println(" times");

      // FLUSH the canvas to display the JPEG!
      Serial.println("Flushing JPEG to display...");
      gfx->flush();

      Serial.println("Image displayed successfully!");
    } else {
      Serial.println("ERROR: JPEG decode failed!");
      displayError("Decode Error");
    }

    // Free buffer
    free(jpegBuffer);

  } else if (httpCode == 404 || httpCode == 503) {
    // 404: No images available
    // 503: Background capture disabled
    Serial.print("Camera not collecting images (HTTP ");
    Serial.print(httpCode);
    Serial.println(")");
    displayNoImages();
  } else {
    Serial.print("HTTP Error: ");
    Serial.println(httpCode);
    displayError("HTTP " + String(httpCode));
  }

  http.end();
}

// ========== TOUCH FUNCTIONS ==========
bool getTouchPoint(uint16_t &x, uint16_t &y) {
    uint8_t data[AXS_MAX_TOUCH_NUMBER * 6 + 2] = {0};

    // Define the read command array properly
    const uint8_t read_cmd[11] = {
        0xb5, 0xab, 0xa5, 0x5a, 0x00, 0x00,
        (uint8_t)((AXS_MAX_TOUCH_NUMBER * 6 + 2) >> 8),
        (uint8_t)((AXS_MAX_TOUCH_NUMBER * 6 + 2) & 0xff),
        0x00, 0x00, 0x00
    };

    Wire.beginTransmission(TOUCH_ADDR);
    Wire.write(read_cmd, 11);
    if (Wire.endTransmission() != 0) return false;

    if (Wire.requestFrom(TOUCH_ADDR, sizeof(data)) != sizeof(data)) return false;

    for (int i = 0; i < sizeof(data); i++) {
        data[i] = Wire.read();
    }

    if (data[1] > 0 && data[1] <= AXS_MAX_TOUCH_NUMBER) {
        uint16_t rawX = ((data[2] & 0x0F) << 8) | data[3];
        uint16_t rawY = ((data[4] & 0x0F) << 8) | data[5];
        if (rawX > 500 || rawY > 500) return false;
        y = map(rawX, 0, 320, 320, 0);
        x = rawY;
        return true;
    }
    return false;
}

// ========== WEATHER FUNCTIONS ==========
void fetchWeatherData() {
  Serial.println("\n--- Fetching weather data ---");

  String url = String(ALLSKY_SERVER) + String(API_WEATHER_ENDPOINT);

  Serial.print("URL: ");
  Serial.println(url);

  http.begin(client, url);
  http.setTimeout(10000);

  int httpCode = http.GET();

  if (httpCode == HTTP_CODE_OK) {
    String payload = http.getString();
    Serial.println("Weather data received");

    // Parse JSON
    StaticJsonDocument<512> doc;
    DeserializationError error = deserializeJson(doc, payload);

    if (!error) {
      currentWeather.description = doc["description"].as<String>();
      currentWeather.temperature = doc["temperature"] | 0.0;
      currentWeather.humidity = doc["humidity"] | 0;
      currentWeather.pressure = doc["pressure"] | 0;
      currentWeather.clouds = doc["clouds"] | 0;
      currentWeather.rain = doc["rain"] | 0.0;
      currentWeather.windSpeed = doc["wind_speed"] | 0.0;
      currentWeather.iconCode = doc["icon_code"].as<String>();

      Serial.println("Weather parsed successfully");
    } else {
      Serial.print("JSON parse error: ");
      Serial.println(error.c_str());
    }
  } else {
    Serial.print("Weather HTTP Error: ");
    Serial.println(httpCode);
  }

  http.end();
}

void displayWeather() {
  Serial.println("Displaying weather...");

  // Set rotation to 1 for landscape weather display
  gfx->setRotation(1);

  gfx->fillScreen(BLACK);
  gfx->setTextColor(WHITE);

  // Title with smooth U8g2 font - moved down to prevent clipping
  gfx->setFont(u8g2_font_helvB14_tr);  // Helvetica Bold 14
  gfx->setCursor(10, 42);  // Was 32, moved down another 10px
  gfx->print("Weather");

  // Weather icon (64x64 bitmap icon in left area)
  drawWeatherIcon(currentWeather.iconCode, 40, 85, 64);  // Was 75, moved down another 10px

  // Description (below icon) with smooth font
  gfx->setFont(u8g2_font_helvR10_tr);  // Helvetica Regular 10
  gfx->setCursor(20, 175);  // Was 165, moved down another 10px
  gfx->print(currentWeather.description);

  // Temperature - large number font
  gfx->setFont(u8g2_font_logisoso26_tn);  // Large number font 26
  gfx->setCursor(230, 95);  // Was 85, moved down another 10px
  gfx->print(currentWeather.temperature, 1);

  // Degree symbol (drawn circle) and C
  gfx->fillCircle(375, 75, 4, WHITE);  // Was 65, moved down another 10px
  gfx->setFont(u8g2_font_helvB14_tr);  // Helvetica Bold 14
  gfx->setCursor(388, 90);  // Was 80, moved down another 10px
  gfx->print("C");

  // Weather details with clean smooth font
  gfx->setFont(u8g2_font_helvR08_tr);  // Helvetica Regular 8
  int detailY = 135;  // Was 125, moved down another 10px
  int detailSpacing = 23;

  // Humidity
  gfx->setCursor(230, detailY);
  gfx->print("Humidity: ");
  gfx->print(currentWeather.humidity);
  gfx->print("%");

  // Wind
  gfx->setCursor(230, detailY + detailSpacing);
  gfx->print("Wind: ");
  gfx->print(currentWeather.windSpeed, 1);
  gfx->print(" m/s");

  // Pressure
  gfx->setCursor(230, detailY + detailSpacing * 2);
  gfx->print("Pressure: ");
  gfx->print(currentWeather.pressure);
  gfx->print(" hPa");

  // Clouds
  gfx->setCursor(230, detailY + detailSpacing * 3);
  gfx->print("Clouds: ");
  gfx->print(currentWeather.clouds);
  gfx->print("%");

  // Back button with polished styling
  gfx->fillRoundRect(10, 250, 150, 60, 10, 0x4228);  // Muted blue button
  gfx->drawRoundRect(10, 250, 150, 60, 10, 0x94B2);  // Gray border
  gfx->drawRoundRect(11, 251, 148, 58, 9, 0x94B2);   // Double border for depth

  gfx->setFont(u8g2_font_helvB12_tr);  // Helvetica Bold 12
  gfx->setCursor(47, 287);  // Adjusted left by width of 'B' (was 55)
  gfx->print("BACK");

  gfx->flush();

  // Reset rotation back to 0 for image display
  gfx->setRotation(0);
  gfx->setFont();  // Reset to default font
}

void drawWeatherIcon(String iconCode, int x, int y, int size) {
  // Draw clean, colorful vector-style weather icons
  int cx = x + size/2;  // Center X
  int cy = y + size/2;  // Center Y
  bool isNight = iconCode.endsWith("n");  // Check if it's nighttime

  if (iconCode.startsWith("01")) {
    // Clear sky - sun (day) or moon (night)
    if (isNight) {
      // Moon - pale yellow crescent
      gfx->fillCircle(cx + 6, cy, 22, 0xFFE0);  // Main moon circle
      gfx->fillCircle(cx + 14, cy - 4, 20, BLACK);  // Shadow to create crescent
      // Add some stars
      gfx->fillCircle(cx - 20, cy - 15, 2, WHITE);
      gfx->fillCircle(cx + 18, cy + 12, 2, WHITE);
      gfx->fillCircle(cx - 12, cy + 18, 2, WHITE);
    } else {
      // Sun - bright yellow with orange center
      gfx->fillCircle(cx, cy, 24, 0xFD20);  // Orange center
      gfx->fillCircle(cx, cy, 18, 0xFFE0);  // Yellow outer

      // Sun rays - 8 directions
      for (int i = 0; i < 8; i++) {
        float angle = i * PI / 4;
        int x1 = cx + cos(angle) * 22;
        int y1 = cy + sin(angle) * 22;
        int x2 = cx + cos(angle) * 30;
        int y2 = cy + sin(angle) * 30;
        gfx->drawLine(x1, y1, x2, y2, 0xFFE0);
        gfx->drawLine(x1+1, y1, x2+1, y2, 0xFFE0);
        gfx->drawLine(x1, y1+1, x2, y2+1, 0xFFE0);
      }
    }

  } else if (iconCode.startsWith("02")) {
    // Few clouds - sun/moon behind cloud
    if (isNight) {
      // Moon (partial, behind cloud)
      gfx->fillCircle(cx - 8, cy - 12, 14, 0xFFE0);
      gfx->fillCircle(cx - 2, cy - 14, 12, BLACK);  // Crescent shadow
    } else {
      // Sun (partial, behind cloud)
      gfx->fillCircle(cx - 12, cy - 12, 16, 0xFFE0);
    }

    // Cloud (white with light gray shadow)
    gfx->fillCircle(cx - 8, cy + 8, 14, 0xCE79);  // Light gray shadow
    gfx->fillCircle(cx + 8, cy + 8, 16, 0xCE79);
    gfx->fillCircle(cx - 8, cy + 6, 14, WHITE);    // White cloud
    gfx->fillCircle(cx + 8, cy + 6, 16, WHITE);
    gfx->fillCircle(cx, cy + 4, 12, WHITE);
    gfx->fillRect(cx - 16, cy + 6, 32, 16, WHITE);

  } else if (iconCode.startsWith("03") || iconCode.startsWith("04")) {
    // Cloudy - fluffy white clouds
    gfx->fillCircle(cx - 14, cy + 4, 12, 0xCE79);  // Shadow
    gfx->fillCircle(cx, cy + 4, 16, 0xCE79);
    gfx->fillCircle(cx + 14, cy + 4, 12, 0xCE79);

    gfx->fillCircle(cx - 14, cy, 12, WHITE);  // White cloud
    gfx->fillCircle(cx, cy, 16, WHITE);
    gfx->fillCircle(cx + 14, cy, 12, WHITE);
    gfx->fillRect(cx - 18, cy, 36, 12, WHITE);

  } else if (iconCode.startsWith("09") || iconCode.startsWith("10")) {
    // Rain - dark cloud with blue rain
    gfx->fillCircle(cx - 12, cy - 8, 12, 0x8C51);  // Dark gray cloud
    gfx->fillCircle(cx + 4, cy - 8, 14, 0x8C51);
    gfx->fillCircle(cx + 12, cy - 8, 10, 0x8C51);
    gfx->fillRect(cx - 14, cy - 8, 26, 10, 0x8C51);

    // Rain drops - bright blue
    for (int i = 0; i < 7; i++) {
      int rx = cx - 18 + i * 6;
      int ry = cy + 4 + (i % 2) * 4;
      gfx->drawLine(rx, ry, rx - 2, ry + 10, 0x1C9F);  // Bright blue
      gfx->drawLine(rx+1, ry, rx - 1, ry + 10, 0x1C9F);
    }

  } else if (iconCode.startsWith("11")) {
    // Thunderstorm - very dark cloud with yellow lightning
    gfx->fillCircle(cx - 12, cy - 8, 12, 0x4208);  // Very dark gray
    gfx->fillCircle(cx + 4, cy - 8, 14, 0x4208);
    gfx->fillCircle(cx + 12, cy - 8, 10, 0x4208);
    gfx->fillRect(cx - 14, cy - 8, 26, 10, 0x4208);

    // Lightning bolt - bright yellow/white
    gfx->fillTriangle(cx - 2, cy + 2, cx - 10, cy + 12, cx - 4, cy + 12, 0xFFE0);
    gfx->fillTriangle(cx - 4, cy + 12, cx + 4, cy + 24, cx - 2, cy + 16, 0xFFE0);

  } else if (iconCode.startsWith("13")) {
    // Snow - light cloud with cyan snowflakes
    gfx->fillCircle(cx - 10, cy - 4, 10, 0xE73C);  // Very light gray
    gfx->fillCircle(cx + 6, cy - 4, 12, 0xE73C);
    gfx->fillRect(cx - 12, cy - 4, 20, 8, 0xE73C);

    // Snowflakes - cyan
    for (int i = 0; i < 5; i++) {
      int sx = cx - 16 + i * 8;
      int sy = cy + 8 + (i % 2) * 6;
      // Draw asterisk pattern
      gfx->drawLine(sx - 3, sy, sx + 3, sy, 0x07FF);  // Cyan
      gfx->drawLine(sx, sy - 3, sx, sy + 3, 0x07FF);
      gfx->drawLine(sx - 2, sy - 2, sx + 2, sy + 2, 0x07FF);
      gfx->drawLine(sx - 2, sy + 2, sx + 2, sy - 2, 0x07FF);
    }

  } else if (iconCode.startsWith("50")) {
    // Mist - gray horizontal lines
    for (int i = 0; i < 8; i++) {
      int my = cy - 20 + i * 6;
      int offset = (i % 2) * 8;
      gfx->drawLine(x + offset, my, x + size - offset - 4, my, 0xBDF7);
      gfx->drawLine(x + offset, my + 1, x + size - offset - 4, my + 1, 0xBDF7);
      gfx->drawLine(x + offset, my + 2, x + size - offset - 4, my + 2, 0x9CF3);
    }

  } else {
    // Default - simple cloud
    gfx->fillCircle(cx - 10, cy, 10, WHITE);
    gfx->fillCircle(cx + 6, cy, 12, WHITE);
    gfx->fillCircle(cx, cy - 4, 11, WHITE);
    gfx->fillRect(cx - 12, cy, 20, 10, WHITE);
  }
}

// ========== DISPLAY NO IMAGES MESSAGE ==========
void displayNoImages() {
  gfx->setRotation(1);  // Landscape for better text display
  gfx->fillScreen(BLACK);

  // Title
  gfx->setFont(u8g2_font_helvB14_tr);
  gfx->setTextColor(0x94B2);  // Light gray
  gfx->setCursor(80, 90);
  gfx->print("AllSky Camera");

  // Message
  gfx->setFont(u8g2_font_helvR10_tr);
  gfx->setTextColor(WHITE);
  gfx->setCursor(50, 130);
  gfx->print("The AllSky camera is currently");
  gfx->setCursor(80, 155);
  gfx->print("not collecting images");

  // Hint text
  gfx->setFont(u8g2_font_helvR08_tr);
  gfx->setTextColor(0x94B2);
  gfx->setCursor(55, 190);
  gfx->print("Enable 'Background Capture' on the");
  gfx->setCursor(95, 210);
  gfx->print("KickPi to start capturing");

  // Icon - simple camera with slash
  int cx = 240;
  int cy = 245;
  gfx->drawRoundRect(cx - 25, cy - 15, 50, 30, 5, 0x94B2);
  gfx->fillCircle(cx, cy, 10, 0x94B2);
  gfx->drawLine(cx - 20, cy - 20, cx + 20, cy + 20, RED);
  gfx->drawLine(cx - 19, cy - 20, cx + 21, cy + 20, RED);
  gfx->drawLine(cx - 20, cy - 19, cx + 20, cy + 21, RED);

  gfx->flush();
  gfx->setRotation(0);  // Reset to portrait
  gfx->setFont();  // Reset to default font

  Serial.println("Displayed: Camera not collecting images");
}

// ========== DISPLAY ERROR MESSAGE ==========
void displayError(String message) {
  gfx->setRotation(1);  // Landscape
  gfx->fillScreen(BLACK);
  gfx->setTextSize(2);
  gfx->setTextColor(RED);
  gfx->setCursor(160, 120);
  gfx->println("ERROR:");
  gfx->setCursor(140, 160);
  gfx->println(message);
  gfx->flush();
  gfx->setRotation(0);  // Reset to portrait

  Serial.print("ERROR: ");
  Serial.println(message);
}
