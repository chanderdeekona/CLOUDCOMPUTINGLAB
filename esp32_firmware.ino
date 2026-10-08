/*
  Cloud Security Alert Lamp - ESP32 Firmware
  Connects ESP32 to AWS IoT Core via WiFi and MQTT.
  Controls physical Red and Green LEDs based on S3 public bucket security detection.
*/

#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// WiFi Configuration
const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// AWS IoT Core Configuration
const char* AWS_IOT_ENDPOINT = "YOUR_ENDPOINT.iot.ap-south-1.amazonaws.com";
const char* AWS_IOT_TOPIC = "security/alert/led";

// Hardware Pin Definitions
const int RED_LED_PIN = 23;    // Red Alert LED
const int GREEN_LED_PIN = 22;  // Green Secure LED

// AWS Certificates (embed your PEM strings here)
static const char AWS_CERT_CA[] PROGMEM = R"EOF(
-----BEGIN CERTIFICATE-----
... Amazon Root CA 1 ...
-----END CERTIFICATE-----
)EOF";

static const char AWS_CERT_CRT[] PROGMEM = R"EOF(
-----BEGIN CERTIFICATE-----
... Device Certificate ...
-----END CERTIFICATE-----
)EOF";

static const char AWS_CERT_PRIVATE[] PROGMEM = R"EOF(
-----BEGIN RSA PRIVATE KEY-----
... Private Key ...
-----END RSA PRIVATE KEY-----
)EOF";

WiFiClientSecure netClient;
PubSubClient mqttClient(netClient);

bool isBlinking = false;
unsigned long lastBlinkTime = 0;
bool ledState = false;

void callback(char* topic, byte* payload, unsigned int length) {
  Serial.print("Message received on topic: ");
  Serial.println(topic);

  StaticJsonDocument<256> doc;
  deserializeJson(doc, payload, length);

  const char* status = doc["status"];
  const char* reason = doc["reason"];

  Serial.print("Status: ");
  Serial.println(status);
  Serial.print("Reason: ");
  Serial.println(reason);

  if (strcmp(status, "BLINKING") == 0) {
    isBlinking = true;
    digitalWrite(GREEN_LED_PIN, LOW);
  } else {
    isBlinking = false;
    digitalWrite(RED_LED_PIN, LOW);
    digitalWrite(GREEN_LED_PIN, HIGH); // System Secure
  }
}

void connectAWS() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  Serial.println("Connecting to WiFi...");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi Connected!");

  netClient.setCACert(AWS_CERT_CA);
  netClient.setCertificate(AWS_CERT_CRT);
  netClient.setPrivateKey(AWS_CERT_PRIVATE);

  mqttClient.setServer(AWS_IOT_ENDPOINT, 8883);
  mqttClient.setCallback(callback);

  Serial.println("Connecting to AWS IoT Core...");
  while (!mqttClient.connect("ESP32_Security_Lamp")) {
    Serial.print(".");
    delay(1000);
  }

  Serial.println("\nConnected to AWS IoT Core!");
  mqttClient.subscribe(AWS_IOT_TOPIC);
  Serial.print("Subscribed to topic: ");
  Serial.println(AWS_IOT_TOPIC);

  // Default secure state
  digitalWrite(GREEN_LED_PIN, HIGH);
  digitalWrite(RED_LED_PIN, LOW);
}

void setup() {
  Serial.begin(115200);
  pinMode(RED_LED_PIN, OUTPUT);
  pinMode(GREEN_LED_PIN, OUTPUT);
  digitalWrite(RED_LED_PIN, LOW);
  digitalWrite(GREEN_LED_PIN, LOW);

  connectAWS();
}

void loop() {
  if (!mqttClient.connected()) {
    connectAWS();
  }
  mqttClient.loop();

  // Handle Red LED Blinking
  if (isBlinking) {
    unsigned long currentMillis = millis();
    if (currentMillis - lastBlinkTime >= 400) {
      lastBlinkTime = currentMillis;
      ledState = !ledState;
      digitalWrite(RED_LED_PIN, ledState ? HIGH : LOW);
    }
  }
}
