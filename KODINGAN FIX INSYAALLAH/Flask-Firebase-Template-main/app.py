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

        h, s, v = colorsys.rgb_to_hsv(r/255.0, g/255.0, b/255.0)

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
        'R': [220, 35, 30],    # Red 2261
        'G': [104, 188, 37],    # Panama Green 1316
        'B': [0, 66, 170],    # Blue Oreo 3428
        'Y': [254, 205, 17],   # Lemon Yellow 3552
        'W': [255, 255, 255],  # White 0001
        'Bl': [10, 10, 10]     # Black 0020

        }

        capacity_ml = request.form.get('capacity', type=float) or 500.0

        # =====================================================================
        # PHASE 1: ADAPTIVE POWER TUNING (p) BERDASARKAN SATURASI
        # =====================================================================
        max_val = max(r, g, b)
        min_val = min(r, g, b)
        saturation = (max_val - min_val) / max_val if max_val > 0 else 0
        p = request.form.get('p_value', type=float) or float(np.clip(2.5 + saturation * 2.5, 2.5, 5.0))


        # =====================================================================
        # PHASE 2: CIEDE76 + HUE-DIRECTION GATE + FILTER THRESHOLD (SMOOTH)
        # =====================================================================
        def smoothstep(x, edge0, edge1):
            if edge1 <= edge0:
                return 1.0 if x >= edge1 else 0.0
            t = np.clip((x - edge0) / (edge1 - edge0), 0.0, 1.0)
            return float(t * t * (3 - 2 * t))

        distances = {}
        weights = {}
        phys_lab_cache = {}

        target_a, target_b_lab = target_lab[1], target_lab[2]
        target_chroma_mag = float(np.hypot(target_a, target_b_lab))

        for name, physical_rgb in TONER_PHYSICAL.items():
            phys_rgb_norm = np.array([[[physical_rgb[0]/255.0, physical_rgb[1]/255.0, physical_rgb[2]/255.0]]])
            phys_lab = rgb2lab(phys_rgb_norm)[0][0]
            phys_lab_cache[name] = phys_lab

            dist = deltaE_cie76(target_lab, phys_lab)
            distances[name] = dist
            weights[name] = 1.0 / ((dist + 0.01) ** p)

            # 🆕 PERBAIKAN 1: BIAS BOBOT MERAH vs KUNING (UNIVERSAL)
            # Pigmen Merah di dunia nyata 2-3x lebih kuat dari Kuning.
            # Jika target oranye, kita naikkan bobot Kuning dan tekan Merah.
            # Jika target MERAH MURNI (jarak 0), bobot Merah tetap ~∞ (tidak rusak).
            if name == 'Y':
                weights[name] *= 2.5
            elif name == 'R':
                weights[name] *= 0.5
            # -------------------------------------------

            if name in ('R', 'G', 'B', 'Y') and target_chroma_mag > 1e-6:
                toner_a, toner_b_lab = phys_lab[1], phys_lab[2]
                toner_mag = np.hypot(toner_a, toner_b_lab)
                if toner_mag > 1e-6:
                    cos_sim = (target_a * toner_a + target_b_lab * toner_b_lab) / (
                        target_chroma_mag * toner_mag
                    )
                else:
                    cos_sim = 0.0
                hue_gate = smoothstep(cos_sim, -0.1, 0.5)
                weights[name] *= hue_gate

        total_weight_all = sum(weights.values())
        if total_weight_all > 0:
            for name in ['R', 'G', 'B', 'Y']:
                proporsi = weights[name] / total_weight_all
                weights[name] *= smoothstep(proporsi, 0.01, 0.05)


        # =====================================================================
        # PHASE 2.5: GRAY HANDLING (SMOOTH, BUKAN ON/OFF)
        # =====================================================================
        gray_fade = smoothstep(saturation, 0.05, 0.15)
        for name in ['R', 'G', 'B', 'Y']:
            weights[name] *= gray_fade


        # =====================================================================
        # PHASE 3: TINTING LOGIC — SATURATION-AWARE (FIXED: POWER 12, EDGE 0.55)
        # =====================================================================
        v = max_val / 255.0
        base_tint = min(0.85, max(0.15, 0.15 + 0.70 * (v ** 12)))
        desaturation_pull = 1.0 - smoothstep(saturation, 0.05, 0.55)
        tint_ratio = base_tint + (1.0 - base_tint) * desaturation_pull
        tint_ratio = min(0.95, tint_ratio)
        chroma_share = 1.0 - tint_ratio


        # =====================================================================
        # PHASE 4: DISTRIBUSI — CHROMA TETAP IDW, W:Bl LINEAR L* + BRIGHTNESS DAMPING
        # =====================================================================
        total_weight_final = sum(weights.values())
        if total_weight_final > 0:
            idw_ratio = {name: weights[name] / total_weight_final for name in TONER_PHYSICAL.keys()}
        else:
            idw_ratio = {name: 0.0 for name in TONER_PHYSICAL.keys()}
            idw_ratio['W'] = 1.0

        chroma_names = ['R', 'G', 'B', 'Y']
        neutral_names = ['W', 'Bl']

        chroma_total = sum(idw_ratio[n] for n in chroma_names)
        chroma_norm = {n: (idw_ratio[n] / chroma_total if chroma_total > 0 else 0.0) for n in chroma_names}

        L_target = target_lab[0]
        L_W = phys_lab_cache['W'][0]
        L_Bl = phys_lab_cache['Bl'][0]

        if L_W > L_Bl:
            w_fraction_linear = float(np.clip((L_target - L_Bl) / (L_W - L_Bl), 0.0, 1.0))
        else:
            w_fraction_linear = 0.5

        brightness_pull = smoothstep(L_target, 45, 75) * (1.0 + saturation) / 2.0
        w_fraction_linear = w_fraction_linear + (1.0 - w_fraction_linear) * brightness_pull
        w_fraction_linear = min(1.0, max(0.0, w_fraction_linear))

        neutral_norm = {'W': w_fraction_linear, 'Bl': 1.0 - w_fraction_linear}

        toner_terkunci = set()

        # =============================================================
        # 🆕 PERBAIKAN 2: LOGIKA HITAM (Bl) UNTUK WARNA TERANG
        # =============================================================
        if v > 0.80 and saturation > 0.50:
            # 🟢 Warna sangat terang & jenuh (oranye/kuning/merah terang)
            # JANGAN paksa Bl = 0. Beri batas maksimal agar warna jadi "bata"
            # tapi jangan terlalu gelap. Maksimal 8% dari total neutral.
            max_bl = 0.08  
            if neutral_norm['Bl'] > max_bl:
                neutral_norm['Bl'] = max_bl
                neutral_norm['W'] = 1.0 - max_bl
            # 🚨 JANGAN tambahkan toner_terkunci.add('Bl') di sini!
            # Biarkan Fase 7 menambahkan Bl sedikit demi sedikit (di bawah 8%)
            # sampai ΔE nya benar-benar pas.

        elif v > 0.65 and saturation > 0.35:
            # Warna medium-terang & jenuh (hijau/biru langit)
            # Tetap batasi 3% dan jangan dikunci.
            if neutral_norm['Bl'] > 0.03:
                neutral_norm['Bl'] = 0.03
                neutral_norm['W'] = 0.97
        # =============================================================

        if chroma_total <= 0:
            chroma_share = 0.0
            tint_ratio = 1.0

        raw_volumes = {}
        for n in chroma_names:
            raw_volumes[n] = chroma_norm[n] * chroma_share * capacity_ml
        for n in neutral_names:
            raw_volumes[n] = neutral_norm[n] * tint_ratio * capacity_ml


        # =====================================================================
        # PHASE 5: LARGEST REMAINDER METHOD (DENGAN HANDLING NEGATIF)
        # =====================================================================
        total_raw = sum(raw_volumes.values())
        if total_raw > 0:
            mix_ratio = {name: raw_volumes.get(name, 0.0) / total_raw for name in TONER_PHYSICAL.keys()}
            exact_volumes = {name: ratio * capacity_ml for name, ratio in mix_ratio.items()}

            mix_ml = {name: int(vol) for name, vol in exact_volumes.items()}

            diff = round(capacity_ml) - sum(mix_ml.values())

            if diff > 0:
                remainders = {name: vol - int(vol) for name, vol in exact_volumes.items()}
                sorted_by_remainder = sorted(remainders.items(), key=lambda x: x[1], reverse=True)
                for i in range(diff):
                    mix_ml[sorted_by_remainder[i % len(sorted_by_remainder)][0]] += 1
            elif diff < 0:
                remainders = {name: vol - int(vol) for name, vol in exact_volumes.items()}
                sorted_by_remainder = sorted(remainders.items(), key=lambda x: x[1])
                i = 0
                sisa = abs(diff)
                while sisa > 0:
                    color = sorted_by_remainder[i % len(sorted_by_remainder)][0]
                    if mix_ml[color] > 0:
                        mix_ml[color] -= 1
                        sisa -= 1
                    i += 1
                    if i > 1000:
                        break
        else:
            mix_ml = {name: 0 for name in TONER_PHYSICAL.keys()}
            mix_ml['W'] = round(capacity_ml)


        # =====================================================================
        # PHASE 6: VERIFIKASI ROUND-TRIP
        # =====================================================================
        total_ml_final = sum(mix_ml.values())
        if total_ml_final > 0:
            predicted_lab = np.zeros(3)
            for name, ml in mix_ml.items():
                predicted_lab += phys_lab_cache[name] * (ml / total_ml_final)
            predicted_delta_e = float(deltaE_cie76(target_lab, predicted_lab))
        else:
            predicted_delta_e = None

        verification = {
            'predicted_lab': predicted_lab.tolist() if total_ml_final > 0 else None,
            'delta_e_prediksi': predicted_delta_e,
            'peringatan': (
                f"ΔE prediksi {predicted_delta_e:.2f} > 5, hasil campuran kemungkinan "
                f"meleset cukup jauh dari target — pertimbangkan kalibrasi ulang."
                if predicted_delta_e is not None and predicted_delta_e > 5 else None
            ),
        }

        # =====================================================================
        # PHASE 7: ITERATIVE REFINEMENT — LOOP SAMPAI ΔE ≤ 5
        # =====================================================================
        def refine_composition(mix_ml_awal, target_lab, phys_lab_cache,
                                target_delta_e=5.0, max_iterations=300,
                                toner_terkunci=None):
            toner_terkunci = toner_terkunci or set()

            def hitung_de(mix):
                total = sum(mix.values())
                if total <= 0:
                    return 999.0, None
                pred_lab = np.zeros(3)
                for name, ml in mix.items():
                    pred_lab += phys_lab_cache[name] * (ml / total)
                return float(deltaE_cie76(target_lab, pred_lab)), pred_lab

            current_mix = dict(mix_ml_awal)
            current_de, current_pred_lab = hitung_de(current_mix)
            nama_toner = list(TONER_PHYSICAL.keys())

            iterasi = 0
            for iterasi in range(1, max_iterations + 1):
                if current_de <= target_delta_e:
                    break

                best_de = current_de
                best_move = None
                best_pred_lab = current_pred_lab

                for donor in nama_toner:
                    if current_mix[donor] <= 0:
                        continue
                    for penerima in nama_toner:
                        if penerima == donor:
                            continue
                        if penerima in toner_terkunci:
                            continue
                        trial = dict(current_mix)
                        trial[donor] -= 1
                        trial[penerima] += 1
                        de, pred_lab = hitung_de(trial)
                        if de < best_de:
                            best_de = de
                            best_move = (donor, penerima)
                            best_pred_lab = pred_lab

                if best_move is None:
                    break

                donor, penerima = best_move
                current_mix[donor] -= 1
                current_mix[penerima] += 1
                current_de = best_de
                current_pred_lab = best_pred_lab

            tercapai = current_de <= target_delta_e
            return current_mix, current_de, iterasi, tercapai


        mix_ml_final, delta_e_final, jumlah_iterasi, tercapai_target = refine_composition(
            mix_ml, target_lab, phys_lab_cache, target_delta_e=5.0,
            max_iterations=300, toner_terkunci=toner_terkunci
        )

        mix_ml = mix_ml_final

        verification['delta_e_prediksi'] = delta_e_final
        verification['delta_e_sebelum_refine'] = predicted_delta_e
        verification['jumlah_iterasi_refine'] = jumlah_iterasi
        verification['target_tercapai'] = tercapai_target
        verification['toner_dikunci'] = list(toner_terkunci)
        verification['peringatan'] = (
            None if tercapai_target else
            f"Sudah dicoba {jumlah_iterasi} iterasi refinement, ΔE terbaik yang bisa "
            f"dicapai adalah {delta_e_final:.2f} (target ≤5). Kemungkinan besar warna "
            f"target ini DI LUAR GAMUT toner yang tersedia, ATAU terkunci oleh aturan "
            f"bisnis ({', '.join(toner_terkunci) if toner_terkunci else 'tidak ada'}) "
            f"— pertimbangkan tambah toner primer baru (Orange/Violet/Cyan)."
        )


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