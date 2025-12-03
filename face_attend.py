import numpy as np
import base64
import cv2
import os
import time
import uuid
import threading
import pygame
from io import BytesIO
from PIL import Image
from deepface import DeepFace
from datetime import datetime
from gtts import gTTS
from ham import get_db_connection

# ---------- CẤU HÌNH NHẬN DIỆN ----------
RECOGNITION_THRESHOLD = 0.8
MODEL_NAME = "ArcFace"

# ---------- CẤU HÌNH ÂM THANH (TTS) ----------
os.makedirs("sound", exist_ok=True)
tts_lock = threading.Lock()
tts_last_spoken = {}  
TTS_COOLDOWN = 3 

def speak_vi_async(text):
    """Phát âm thanh Tiếng Việt không chặn luồng chính"""
    if not text: return
    now = time.time()
    last = tts_last_spoken.get(text, 0)
    if now - last < TTS_COOLDOWN:
        return
    tts_last_spoken[text] = now

    def _worker(msg):
        try:
            fname = os.path.join("sound", f"tts_{uuid.uuid4().hex}.mp3")
            tts = gTTS(text=msg, lang="vi")
            tts.save(fname)
            try:
                if not pygame.mixer.get_init(): pygame.mixer.init()
                while pygame.mixer.music.get_busy(): time.sleep(0.1)
                pygame.mixer.music.load(fname)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy(): time.sleep(0.1)
                pygame.mixer.music.unload()
                try: os.remove(fname)
                except: pass
            except Exception as e: print("Pygame error:", e)
        except Exception as e: print("gTTS error:", e)

    threading.Thread(target=_worker, args=(text,), daemon=True).start()

# ---------- XỬ LÝ ẢNH ----------

def read_b64_image(b64str):
    try:
        if ',' in b64str: b64data = b64str.split(',', 1)[1]
        else: b64data = b64str
        img_bytes = base64.b64decode(b64data)
        img = Image.open(BytesIO(img_bytes)).convert("RGB")
        return np.array(img)[:, :, ::-1] 
    except Exception as e:
        print(f"Lỗi đọc ảnh: {e}")
        return None

def cosine_similarity(a, b):
    a = a.flatten()
    b = b.flatten()
    if np.linalg.norm(a) == 0 or np.linalg.norm(b) == 0: return -1
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

def get_face_embedding(img_array):
    try:
        embedding_objs = DeepFace.represent(
            img_path=img_array,
            model_name=MODEL_NAME,
            detector_backend="opencv", 
            enforce_detection=True,
            align=True
        )
        if len(embedding_objs) > 0:
            return np.array(embedding_objs[0]["embedding"], dtype=np.float32)
        return None
    except Exception as e:
        return None

# --- CHỨC NĂNG 1: ĐĂNG KÝ ---
def luu_khuon_mat_db(ma_nv, image_base64):
    img_arr = read_b64_image(image_base64)
    if img_arr is None: return False, "Ảnh lỗi"

    emb = get_face_embedding(img_arr)
    if emb is None: return False, "Không tìm thấy khuôn mặt rõ ràng"

    conn = get_db_connection()
    if not conn: return False, "Lỗi kết nối DB"
    
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM FaceData WHERE MaNV = ?", (ma_nv,))
        emb_bytes = emb.tobytes()
        cursor.execute("INSERT INTO FaceData (MaNV, Embedding) VALUES (?, ?)", (ma_nv, emb_bytes))
        conn.commit()
        
        speak_vi_async("Đăng ký thành công")
        return True, "Đăng ký thành công!"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

# --- CHỨC NĂNG 2: CHẤM CÔNG ---
def cham_cong_bang_khuon_mat(image_base64):
    img_arr = read_b64_image(image_base64)
    if img_arr is None: return {"status": "error", "message": "Ảnh lỗi"}

    target_emb = get_face_embedding(img_arr)
    if target_emb is None: return {"status": "error", "message": "Không thấy mặt"}

    conn = get_db_connection()
    if not conn: return {"status": "error", "message": "Lỗi DB"}

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT f.MaNV, e.HoTen, f.Embedding FROM FaceData f JOIN Employee e ON f.MaNV = e.MaNV")
        rows = cursor.fetchall()
        
        best_score = -1
        found_user = None

        for row in rows:
            ma_nv, ho_ten, emb_blob = row
            if not emb_blob: continue
            db_emb = np.frombuffer(emb_blob, dtype=np.float32)
            score = cosine_similarity(target_emb, db_emb)
            if score > best_score:
                best_score = score
                found_user = {'ma_nv': ma_nv, 'ho_ten': ho_ten}

        if best_score > RECOGNITION_THRESHOLD and found_user:
            return thuc_hien_log_db(conn, found_user)
        else:
            return {"status": "unknown", "message": "Không nhận diện được", "score": best_score}

    finally:
        conn.close()

def thuc_hien_log_db(conn, user):
    """Ghi log với logic thời gian chặt chẽ: 10p Check-out, 30p Re Check-in"""
    try:
        cursor = conn.cursor()
        ma_nv = user['ma_nv']
        ten_nv = user['ho_ten']
        today = datetime.now().date()
        now = datetime.now()
        
        # Lấy bản ghi chấm công MỚI NHẤT trong ngày của nhân viên này
        cursor.execute("""
            SELECT TOP 1 LogId, CheckIn, CheckOut 
            FROM AttendLog 
            WHERE MaNV = ? AND CAST(CheckIn AS DATE) = ? 
            ORDER BY CheckIn DESC
        """, (ma_nv, today))
        
        row = cursor.fetchone()
        
        msg_text = ""
        msg_speak = ""
        type_cc = ""
        status = "success"
        
        # --- TRƯỜNG HỢP 1: Chưa chấm công lần nào trong ngày ---
        if not row:
            cursor.execute("INSERT INTO AttendLog (MaNV, CheckIn) VALUES (?, GETDATE())", (ma_nv,))
            msg_text = f"Xin chào {ten_nv}, Check-in thành công!"
            msg_speak = f"Xin chào {ten_nv}"
            type_cc = "Check-in"
            
        # --- TRƯỜNG HỢP 2: Đã Check-in, đang đợi Check-out (Bản ghi mở) ---
        elif row.CheckIn and not row.CheckOut:
            # Tính thời gian từ lúc Check-in
            minutes_diff = (now - row.CheckIn).total_seconds() / 60
            
            if minutes_diff < 5:
                wait_min = int(10 - minutes_diff) + 1
                msg_text = f"Bạn mới vào làm. Vui lòng đợi {wait_min} phút nữa để Check-out."
                msg_speak = f"Vui lòng đợi {wait_min} phút để check out"
                status = "warning"
            else:
                cursor.execute("UPDATE AttendLog SET CheckOut = GETDATE() WHERE LogId = ?", (row.LogId,))
                msg_text = f"Tạm biệt {ten_nv}, Check-out thành công!"
                msg_speak = f"Tạm biệt {ten_nv}"
                type_cc = "Check-out"
                
        # --- TRƯỜNG HỢP 3: Đã Check-out rồi (Muốn vào ca tiếp theo) ---
        elif row.CheckOut:
            # Tính thời gian từ lúc Check-out gần nhất
            minutes_diff = (now - row.CheckOut).total_seconds() / 60
            
            if minutes_diff < 5:
                wait_min = int(5 - minutes_diff) + 1
                msg_text = f"Bạn vừa Check-out. Vui lòng đợi {wait_min} phút nữa để Check-in lại."
                msg_speak = f"Vui lòng đợi {wait_min} phút để check in lại"
                status = "warning"
            else:
                cursor.execute("INSERT INTO AttendLog (MaNV, CheckIn) VALUES (?, GETDATE())", (ma_nv,))
                msg_text = f"Xin chào {ten_nv}, Check-in (Ca tiếp) thành công!"
                msg_speak = f"Xin chào {ten_nv}, ca tiếp theo"
                type_cc = "Check-in"
            
        if status == "success":
            conn.commit()
        
        speak_vi_async(msg_speak)
        
        return {"status": status, "message": msg_text, "user": ten_nv, "type": type_cc}
        
    except Exception as e:
        print(e)
        return {"status": "error", "message": str(e)}