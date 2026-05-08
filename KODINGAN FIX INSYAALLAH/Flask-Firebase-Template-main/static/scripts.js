// ===============================
// 🔗  MQTT CONFIG
// ===============================

// --- GANTI dengan URL HiveMQ Websocket broker lo
const MQTT_URL = "wss://427b150a5b914524907cc3238ef56ef8.s1.eu.hivemq.cloud:8884/mqtt";


// --- GANTI dengan user & password HiveMQ lo
const MQTT_USER = "Dede_Irwan";
const MQTT_PASS = "Smartpaint122";

// --- Topic standar komunikasi SmartPaint
const TOPIC_CMD = "smartpaint/cmd";        // web → esp32
const TOPIC_STATUS = "smartpaint/status";  // esp32 → web
const TOPIC_LOG = "smartpaint/log";        // monitoring

console.log("🚀 Connecting to MQTT...");

const client = mqtt.connect(MQTT_URL, {
    username: MQTT_USER,
    password: MQTT_PASS,
});

// --- Status MQTT
client.on("connect", () => {
    console.log("🔥 MQTT Connected!");
    client.subscribe(TOPIC_STATUS);
    client.subscribe(TOPIC_LOG);
});

client.on("error", err => console.error("❌ MQTT Error:", err));

client.on("message", (topic, msg) => {
    console.log(`📩 MQTT IN [${topic}] →`, msg.toString());
});


// ===============================
// 📤  PUBLISH COLOR DATA FUNCTION
// ===============================

function sendRGBtoESP(payload) {
    if (!client.connected) {
        console.warn("⚠ MQTT Not connected — retrying...");
        return;
    }

    const jsonData = JSON.stringify(payload);
    client.publish(TOPIC_CMD, jsonData);
    console.log(`📤 MQTT → ESP: ${jsonData}`);
}


// ===============================
// 🎨  SEND FINAL MIX DATA
// ===============================

function publishDetectedColor(r, g, b, y, w, bl) {
    const data = { R: r, G: g, B: b, Y: y, W: w, Bl: bl };
    sendRGBtoESP(data);
}


// ===============================
// 🧭 UI Logic (Original Code)
// ===============================

// Toggle hamburger button
document.querySelector('.hamburger')?.addEventListener('click', function() {
    const navRight = document.getElementById('navbarRight');
    navRight.style.left = (navRight.style.left === "0px") ? "-100%" : "0";
});

// Close side menu
document.querySelector('.closebtn')?.addEventListener('click', function() {
    document.getElementById('navbarRight').style.left = "-100%";
});

// Dropdown menu
const dropBtn = document.getElementById('dropBtn');
if (dropBtn) {
    const dropdownContent = document.querySelector('.dropdown-content');
    dropBtn.addEventListener('click', () => {
        dropdownContent.style.display =
            dropdownContent.style.display === "none" ? "block" : "none";
    });
}


// ===============================
// 📦 UPLOAD HANDLER (Original)
// ===============================

document.addEventListener("DOMContentLoaded", function () {

    document.getElementById("uploadBtn")?.addEventListener("click", async function () {

        let capacity = parseFloat(document.getElementById("kapasitasSelect").value);
        if (isNaN(capacity)) capacity = 500;

        const formData = new FormData();
        formData.append("capacity", capacity);

        try {
            const res = await fetch("/upload", { method: "POST", body: formData });
            const data = await res.json();

            console.log("📁 Result from server:", data);

            // 👉 SEND TO MQTT FOR ESP32
            publishDetectedColor(
                data.mix_ml.R,
                data.mix_ml.G,
                data.mix_ml.B,
                data.mix_ml.Y,
                data.mix_ml.W,
                data.mix_ml.Bl
            );

            alert(`Upload berhasil! Total: ${
                Object.values(data.mix_ml).reduce((a,b)=>a+b,0)
            } ml`);

        } catch (err) {
            console.error("❌ Upload Error:", err);
            alert("Upload gagal!");
        }
    });

});
