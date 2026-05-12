from flask import Flask, redirect, render_template, request, make_response, session, jsonify, url_for
import secrets
from functools import wraps
from datetime import timedelta
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore, auth, db as rtdb
import os
from dotenv import load_dotenv
import numpy as np
from PIL import Image
from skimage import color
import json
import ssl
import paho.mqtt.publish as publish  # pip install paho-mqtt
import os
from werkzeug.utils import secure_filename
from datetime import datetime


# -------------------------------
# Load Environment & Setup Flask
# -------------------------------
load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'supersecretkey')

# -------------------------------
# Session Config
# -------------------------------
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=1)
app.config['SESSION_REFRESH_EACH_REQUEST'] = True

# -------------------------------
# Firebase Setup
# -------------------------------
cred = credentials.Certificate("firebase-auth.json")
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred, {
        "databaseURL": "https://deteksi-body-default-rtdb.asia-southeast1.firebasedatabase.app/"
    })

firestore_db = firestore.client()
db = firestore_db
realtime_db = rtdb.reference("/")

# -------------------------------
# Middleware Auth
# -------------------------------
def auth_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ===============================
# BATAS AKUN GOOGLE (WHITELIST)
# ===============================

ALLOWED_USERS = [
    "2210631160027@student.unsika.ac.id",
    "2210631160033@student.unsika.ac.id",
    "2210631160032@student.unsika.ac.id"
]

# -------------------------------
# AUTH ROUTES
# -------------------------------
from flask import request, jsonify, session
from firebase_admin import auth

@app.route('/auth', methods=['POST'])
def authorize():

    data = request.get_json(silent=True)

    if data:
        id_token = data.get('idToken')
    else:
        id_token = request.form.get('idToken')

    if not id_token:
        print("❌ ID TOKEN TIDAK DITERIMA")
        return jsonify({"error": "Token tidak ditemukan"}), 400

    try:
        decoded_token = auth.verify_id_token(id_token, clock_skew_seconds=60)
        user_email = decoded_token.get("email").lower().strip()

        print("LOGIN EMAIL:", user_email)

        if user_email not in ALLOWED_USERS:
            print("⛔ DITOLAK:", user_email)
            return jsonify({"error": "Akses ditolak"}), 403

        session['user'] = {
            "email": user_email,
            "uid": decoded_token.get("uid")
        }

        print("✅ LOGIN BERHASIL")
        return jsonify({"success": True})

    except Exception as e:
        print("🔥 AUTH ERROR:", e)
        return jsonify({"error": str(e)}), 401
    
# -------------------------------
# PUBLIC ROUTES
# -------------------------------
@app.route('/')
def home():
    return render_template('home.html')

@app.route('/login')
def login():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/signup')
def signup():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    return render_template('signup.html')

@app.route('/reset-password')
def reset_password():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    return render_template('forgot_password.html')

@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    response = make_response(redirect(url_for('login')))
    response.set_cookie('session', '', expires=0)
    return response

# -------------------------------
# PRIVATE ROUTES
# -------------------------------
@app.route('/dashboard')
@auth_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/detect')
@auth_required
def detect():
    return render_template('detect.html')

@app.route('/monitoring')
@auth_required
def monitoring():
    return render_template('monitoring.html')

@app.route('/history')
@auth_required
def history():
    user = session.get('user')
    user_id = user.get('uid')
    records = []

    try:
        docs = db.collection('color_detections') \
            .where('user_id', '==', user_id) \
            .order_by('timestamp', direction=firestore.Query.DESCENDING) \
            .stream()

        for doc in docs:
            data = doc.to_dict()

            # 1. Pastikan timestamp aman
            if 'timestamp' in data and data['timestamp']:
                try:
                    data['timestamp'] = data['timestamp'].strftime("%d-%m-%Y %H:%M:%S")
                except: pass
            else:
                data['timestamp'] = "Tanpa Waktu"

            # 2. PROTEKSI RGB_NORMALIZE (Inilah penyebab error di screenshot)
            # Kita cari di 'rgb' atau 'rgb_normalize'. Kalau gak ada dua-duanya, kasih 0.
            raw_rgb = data.get("rgb") or data.get("rgb_normalize") or {}
            data["rgb_normalize"] = {
                "r": raw_rgb.get('r', 0),
                "g": raw_rgb.get('g', 0),
                "b": raw_rgb.get('b', 0)
            }

            # 3. PROTEKSI MIX_ML
            m = data.get("mix_ml", {})
            # Pastikan semua key kapital tersedia untuk HTML
            data["mix_ml"] = {
                "R": m.get("R", m.get("r", 0)),
                "G": m.get("G", m.get("g", 0)),
                "B": m.get("B", m.get("b", 0)),
                "Y": m.get("Y", m.get("y", 0)),
                "W": m.get("W", m.get("w", 0)),
                "Bl": m.get("Bl", m.get("bl", 0))
            }

            records.append(data)

    except Exception as e:
        print(f"Error Sistem History: {e}")

    # Kirim ke template (Hapus |reverse di HTML jika datanya jadi terbalik)
    return render_template('history.html', records=records)

# -------------------------------
# UPLOAD & DETEKSI WARNA (VERSI FIX)
# -------------------------------
@app.route('/upload', methods=['POST'])
@auth_required
def upload_color_image():
    if 'file' not in request.files:
        return jsonify({'error': 'No file received'}), 400

    file = request.files['file']
    img = Image.open(file.stream).convert('RGB')
    img_np = np.array(img)

    # 1. AMBIL WARNA RATA-RATA DARI GAMBAR (TARGET)
    avg_color = img_np.mean(axis=(0, 1)).astype(np.uint8)
    r, g, b = avg_color.tolist() # Kita pakai r, g, b agar sinkron dengan frontend

    # 2. HITUNG NILAI LAB (Untuk keperluan Database/Display)
    rgb_normalized = np.array([[[r/255, g/255, b/255]]])
    lab_vals = color.rgb2lab(rgb_normalized)[0][0]
    L, a_val, b_lab = lab_vals.tolist()

    # 3. DEFINISIKAN WARNA ASLI TONER FISIK (KALIBRASI)
    TONER_PHYSICAL = {
        'R':  [220, 30, 20],   # Ganti sesuai hasil foto toner asli kamu
        'G':  [40, 210, 50],   
        'B':  [30, 40, 180],   
        'Y':  [240, 230, 10],  
        'W':  [250, 250, 250], 
        'Bl': [15, 15, 15]     
    }

    capacity_ml = request.form.get('capacity', type=float) or 500.0

    # 4. LOGIKA PENCAMPURAN (INVERSE DISTANCE WEIGHTING)
    weights = {}
    total_weight = 0

# Tentukan nilai p (semakin tinggi, semakin tajam/akurat pemisahan warnanya)
    p = 3

    for name, physical_rgb in TONER_PHYSICAL.items():
        # 1. Hitung jarak (tetap sama)
        distance = np.sqrt((r - physical_rgb[0])**2 + (g - physical_rgb[1])**2 + (b - physical_rgb[2])**2)
        
        # 2. UBAH BARIS INI: Tambahkan pangkat (** p)
        # Kita pakai (distance + 0.1) agar jika jaraknya 0, tidak terjadi error pembagian
        weight = 1.0 / ((distance + 0.1) ** p)
        
        weights[name] = weight
        total_weight += weight

    # 5. GENERATE RATIO & ML
    mix_ratio = {name: round(w / total_weight, 4) for name, w in weights.items()}
    mix_ml = {name: round((w / total_weight) * capacity_ml, 2) for name, w in weights.items()}

    # 6. SIMPAN GAMBAR KE STATIC
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    new_filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{secure_filename(file.filename)}"
    file_path = os.path.join(BASE_DIR, 'static', 'history', new_filename)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    img.save(file_path)

    # 7. SIMPAN KE FIRESTORE & REALTIME DB
    user = session.get('user')
    user_id = user.get('uid')
    
    # Ambil waktu sekarang
    now = datetime.utcnow()

    # Data untuk Database (Boleh pakai objek datetime asli)
    db_data = {
        'user_id': user_id,
        'timestamp': now, 
        'image': new_filename,
        'rgb': {'r': int(r), 'g': int(g), 'b': int(b)},
        'lab': {'L': round(L,2), 'a': round(a_val,2), 'b': round(b_lab,2)},
        'mix_ratio': mix_ratio,
        'mix_ml': mix_ml
    }
    
    db.collection('color_detections').add(db_data)
    
    # Untuk Realtime DB & JSON Response, timestamp harus jadi STRING
    # Kita buat salinan data khusus untuk dikirim keluar
    json_data = db_data.copy()
    json_data['timestamp'] = now.strftime("%Y-%m-%d %H:%M:%S") # Ubah datetime ke teks

    realtime_db.child("color_detection").set(json_data)

    # 8. KIRIM RESPON KE FRONTEND
    return jsonify({
        'status': 'success',
        'rgb': [int(r), int(g), int(b)],
        'lab': [round(L,2), round(a_val,2), round(b_lab,2)],
        'mix_ratio': mix_ratio,
        'mix_ml': mix_ml,
        'timestamp': json_data['timestamp'] # Kirim versi teksnya
    })

# -------------------------------
# ROUTE MQTT PUBLISH
# -------------------------------
@app.route('/mqtt_publish', methods=['POST'])
@auth_required
def mqtt_publish_route():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data received'}), 400

    try:
        import ssl
        import json
        import paho.mqtt.publish as publish

        # Pastikan data yang dikirim hanya mix_ml
        payload = data  # frontend harus mengirim data.mix_ml

        publish.single(
            topic="smartpaint/cmd",
            payload=json.dumps(payload),
            hostname="427b150a5b914524907cc3238ef56ef8.s1.eu.hivemq.cloud",
            port=8883,
            auth={'username': 'Dede_Irwan', 'password': 'Smartpaint122'},
            tls={'ca_certs': None, 'certfile': None, 'keyfile': None, 
                 'tls_version': ssl.PROTOCOL_TLS, 'ciphers': None}
        )

        return jsonify({'status': 'ok'})

    except Exception as e:
        print("MQTT publish error:", e)
        return jsonify({'error': str(e)}), 500

# -------------------------------
# TEST FIREBASE CONNECTION
# -------------------------------
@app.route('/test_firebase')
def test_firebase():
    try:
        firestore_db.collection("test").add({"msg": "Hello Firestore"})
        realtime_db.child("test").set({"msg": "Hello Realtime"})
        return "✅ Firebase Firestore & Realtime Database terhubung!"
    except Exception as e:
        return f"❌ Error: {e}"

# -------------------------------
# RUN APP
# -------------------------------
if __name__ == '__main__':
    app.run(debug=True)