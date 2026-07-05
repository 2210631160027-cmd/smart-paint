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
from skimage.color import rgb2lab, deltaE_cie76
import json
import ssl
import paho.mqtt.publish as publish  # pip install paho-mqtt
from werkzeug.utils import secure_filename
import colorsys  # WAJIB UNTUK SISTEM ADAPTIF HSV
from skimage.color import rgb2lab, lab2rgb
import time






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
    "2210631160032@student.unsika.ac.id",
    "2210631160033@student.unsika.ac.id"
   
]




# -------------------------------
# AUTH ROUTES
# -------------------------------
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


@app.route('/about')
def about():
    return render_template('about.html')


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
            data['id'] = doc.id




            if 'timestamp' in data and data['timestamp']:
                try:
                    data['timestamp'] = data['timestamp'].strftime("%d-%m-%Y %H:%M:%S")
                except: pass
            else:
                data['timestamp'] = "Tanpa Waktu"

            # --- AMANKAN VARIABEL RGB UNTUK JINJA ---
            raw_rgb = data.get("rgb") or data.get("rgb_normalize") or {}
           
            data["rgb"] = {
                "r": raw_rgb.get('r', raw_rgb.get('R', 0)),
                "g": raw_rgb.get('g', raw_rgb.get('G', 0)),
                "b": raw_rgb.get('b', raw_rgb.get('B', 0))
            }
           
            data["rgb_normalize"] = {
                "r": data["rgb"]["r"],
                "g": data["rgb"]["g"],
                "b": data["rgb"]["b"]
            }
            m = data.get("mix_ml", {})
            data["mix_ml"] = {
                "R": m.get("R", m.get("r", 0)),
                "G": m.get("G", m.get("g", 0)),
                "B": m.get("B", m.get("b", 0)),
                "Y": m.get("Y", m.get("y", 0)),
                "W": m.get("W", m.get("w", 0)),
                "Bl": m.get("Bl", m.get("bl", 0))
            }
           
            if 'p_value' not in data:
                data['p_value'] = 2

            records.append(data)

    except Exception as e:
        print(f"Error Sistem History: {e}")

    return render_template('history.html', records=records)

@app.route('/delete_history/<doc_id>', methods=['POST'])
@auth_required
def delete_history_item(doc_id):
    try:
        db.collection('color_detections').document(doc_id).delete()
        return jsonify({'status': 'success', 'message': 'Riwayat berhasil dihapus'})
    except Exception as e:
        print(f"🔥 Error Hapus: {e}")
        return jsonify({'error': str(e)}), 500

# -------------------------------
# UPLOAD & DETEKSI WARNA (HYBRID IDW + HSV PENALTY)
# -------------------------------
@app.route('/upload', methods=['POST'])
@auth_required
def upload_color_image():
    if 'file' not in request.files:
        return jsonify({'error': 'No file received'}), 400

    try:
        # 1. NYALAKAN STOPWATCH TEPAT SETELAH MASUK TRY
        start_time = time.time()

        file = request.files['file']
        img = Image.open(file.stream).convert('RGB')
        img_np = np.array(img)

        # 1. SPATIAL AVERAGING (10x10 PIXELS AT MIDPOINT)
        height, width, _ = img_np.shape
        center_x, center_y = width // 2, height // 2
        radius = int(min(width, height) * 0.05) # Mengambil 5% dari dimensi terkecil gambar
       
        y_start = max(0, center_y - radius)
        y_end = min(height, center_y + radius)
        x_start = max(0, center_x - radius)
        x_end = min(width, center_x + radius)
       
        roi = img_np[y_start:y_end, x_start:x_end]
        avg_color = np.mean(roi, axis=(0, 1)).astype(np.uint8)
        r_raw, g_raw, b_raw = int(avg_color[0]), int(avg_color[1]), int(avg_color[2])
               
        r = int(avg_color[0])  
        g = int(avg_color[1])  
        b = int(avg_color[2])  

        # ==========================================
        # 2. KONVERSI RGB -> LAB
        # ==========================================
        rgb_normalized = np.array([[[r/255.0, g/255.0, b/255.0]]])
        lab_vals = rgb2lab(rgb_normalized)[0][0]
        L, a_val, b_lab = lab_vals.tolist()


        L_calibrated = L
        a_calibrated = a_val
        b_calibrated = b_lab
       
        # ==========================================
        # 3. TARGET LAB (LANGSUNG DARI RGB)
        # ==========================================
        target_rgb_norm = np.array([[[r/255.0, g/255.0, b/255.0]]])
        target_lab = rgb2lab(target_rgb_norm)[0][0]

        # ==========================================
        #  FINAL LAB UNTUK HISTORY/DATABASE 
        # ==========================================
        final_L = target_lab[0]
        final_a = target_lab[1]
        final_b = target_lab[2]

        # ATAU jika mau simpan yang sudah dikalibrasi:
        lab_final = [L_calibrated, a_calibrated, b_calibrated]

        # =====================================================================
        # 3. KOORDINAT RIIL TONER FISIK (KALIBRASI & KOMPENSASI EUCLIDEAN)
        # =====================================================================
        TONER_PHYSICAL = {
            'R': [242, 48, 30],
            'G': [117, 193, 47],
            'B': [37, 61, 171],
            'Y': [252, 205, 54],
            'W': [254, 254, 243],
            'Bl': [2, 1, 0]
        }


        capacity_ml = request.form.get('capacity', type=float) or 500.0

        # =====================================================================
        # PHASE 1: ADAPTIVE POWER TUNING (p) BERDASARKAN SATURASI
        # =====================================================================
        max_val = max(r, g, b)
        min_val = min(r, g, b)
        saturation = (max_val - min_val) / max_val if max_val > 0 else 0
        p = request.form.get('p_value', type=float) or float(np.clip(1.5 + saturation * 1.5, 1.5, 4.0))


        # =====================================================================
        # PHASE 2: CIEDE2000 + FILTER THRESHOLD
        # =====================================================================
        distances = {}
        weights = {}


        for name, physical_rgb in TONER_PHYSICAL.items():
            phys_rgb_norm = np.array([[[physical_rgb[0]/255.0, physical_rgb[1]/255.0, physical_rgb[2]/255.0]]])
            phys_lab = rgb2lab(phys_rgb_norm)[0][0]
            dist = deltaE_cie76(target_lab, phys_lab)  
            distances[name] = dist
            weights[name] = 1.0 / ((dist + 0.01) ** p)


        # Filter threshold 5%
        total_weight = sum(weights.values())
        for name in list(weights.keys()):
            if weights[name] / total_weight < 0.05:
                weights[name] = 0.0


        # =====================================================================
        # PHASE 3: TINTING LOGIC (KOREKSI)
        # =====================================================================
        h, s, v = colorsys.rgb_to_hsv(r/255.0, g/255.0, b/255.0)


        # Putih: semakin terang & rendah saturasi
        w_ratio = (v ** 1.5) * ((1.0 - s) ** 1.2)


        # Hitam: hanya untuk warna gelap & kusam
        # (DIPATCH: hard threshold v<0.6 dan s<0.4 diganti sigmoid kontinu,
        #  supaya tidak ada cliff/lompatan tiba-tiba di sekitar batas tersebut)
        dark_factor = 1.0 / (1.0 + np.exp((v - 0.6) / 0.08))   # smooth di sekitar v=0.6
        dull_factor = 1.0 / (1.0 + np.exp((s - 0.4) / 0.08))   # smooth di sekitar s=0.4
        bl_ratio = ((1.0 - v) ** 2) * 1.5 * (1.0 - s) * dark_factor * dull_factor


        # Normalisasi tinting
        total_tints = w_ratio + bl_ratio
        if total_tints > 0:
            tint_ratio = min(0.85, total_tints / (total_tints + 1.0))
        else:
            tint_ratio = 0.0


        tint_amount = tint_ratio * capacity_ml
        sisa_kapasitas = capacity_ml - tint_amount


        # =====================================================================
        # PHASE 4: DISTRIBUSI PRIMER DENGAN SPILLOVER AMAN
        # =====================================================================
        total_hue_weight = sum([weights.get(n, 0.0) for n in ['R', 'G', 'B', 'Y']])
        raw_volumes = {}


        if total_hue_weight > 0:
            chromatic_multiplier = 1.0 - np.exp(-s * 30.0)
            for n in ['R', 'G', 'B', 'Y']:
                base_vol = (weights.get(n, 0.0) / total_hue_weight) * sisa_kapasitas
                raw_volumes[n] = base_vol * max(0.1, chromatic_multiplier)
           
            # Normalisasi jika overflow
            total_primary = sum(raw_volumes.values())
            if total_primary > sisa_kapasitas:
                scale = sisa_kapasitas / total_primary
                for n in ['R', 'G', 'B', 'Y']:
                    raw_volumes[n] *= scale
                volume_tertahan = 0.0
            else:
                volume_tertahan = sisa_kapasitas - total_primary
        else:
            volume_tertahan = sisa_kapasitas
            for n in ['R', 'G', 'B', 'Y']:
                raw_volumes[n] = 0.0


        # Distribusi tinting
        if total_tints > 0:
            raw_volumes['W'] = (w_ratio / total_tints) * (tint_amount + volume_tertahan)
            raw_volumes['Bl'] = (bl_ratio / total_tints) * (tint_amount + volume_tertahan)
        else:
            raw_volumes['W'] = 0.0
            raw_volumes['Bl'] = 0.0


        # =====================================================================
        # PHASE 5: LARGEST REMAINDER METHOD (DENGAN HANDLING NEGATIF)
        # =====================================================================
        total_raw = sum(raw_volumes.values())
        if total_raw > 0:
            mix_ratio = {name: raw_volumes.get(name, 0.0) / total_raw for name in TONER_PHYSICAL.keys()}
            exact_volumes = {name: ratio * capacity_ml for name, ratio in mix_ratio.items()}
           
            # Pembulatan awal
            mix_ml = {name: int(vol) for name, vol in exact_volumes.items()}
           
            # Distribusi sisa atau pengurangan
            diff = round(capacity_ml) - sum(mix_ml.values())
           
            if diff > 0:
                remainders = {name: vol - int(vol) for name, vol in exact_volumes.items()}
                sorted_by_remainder = sorted(remainders.items(), key=lambda x: x[1], reverse=True)
                for i in range(diff):
                    mix_ml[sorted_by_remainder[i][0]] += 1
            elif diff < 0:
                remainders = {name: vol - int(vol) for name, vol in exact_volumes.items()}
                sorted_by_remainder = sorted(remainders.items(), key=lambda x: x[1])
                for i in range(abs(diff)):
                    color = sorted_by_remainder[i][0]
                    if mix_ml[color] > 0:
                        mix_ml[color] -= 1

        # 6. SIMPAN GAMBAR KE STATIC
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        new_filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{secure_filename(file.filename)}"
        file_path = os.path.join(BASE_DIR, 'static', 'history', new_filename)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        img.save(file_path)

        # =====================================================================
        # 7. MATIKAN STOPWATCH & SIMPAN KE FIREBASE
        # =====================================================================
        end_time = time.time()
        waktu_proses_ms = round((end_time - start_time) * 1000, 2)
        user = session.get('user')
        user_id = user.get('uid')
        now = datetime.utcnow()
        db_data = {
            'user_id': user_id,
            'timestamp': now,
            'image': new_filename,
            'rgb': {'r': r, 'g': g, 'b': b},
            'lab': {'L': round(L,2), 'a': round(a_val,2), 'b': round(b_lab,2)},
            'mix_ratio': mix_ratio,
            'mix_ml': mix_ml,
            'p_value': p,
            'waktu_proses_ms': waktu_proses_ms  # Waktu proses berhasil disisipkan di sini
        }
        db.collection('color_detections').add(db_data)
       
        json_data = db_data.copy()
        json_data['timestamp'] = now.strftime("%Y-%m-%d %H:%M:%S")
        realtime_db.child("color_detection").set(json_data)

        # Kembalikan waktu_proses_ms ke frontend
        return jsonify({
            'status': 'success', 'rgb': [r, g, b],
            'lab': [round(L,2), round(a_val,2), round(b_lab,2)],
            'mix_ratio': mix_ratio, 'mix_ml': mix_ml,
            'p_value': p,
            'waktu_proses_ms': waktu_proses_ms,
            'timestamp': json_data['timestamp']
        })

    except Exception as e:
        print(f"🔥 Error Upload: {e}")
        return jsonify({'error': str(e)}), 500

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
        payload = data  
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
