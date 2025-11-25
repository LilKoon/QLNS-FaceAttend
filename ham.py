# trong file ham.py
import pyodbc
from werkzeug.security import check_password_hash, generate_password_hash # Rất quan trọng cho bảo mật

# --- Cấu hình kết nối MS SQL Server ---
# (Hãy đảm bảo bạn đã cài đặt ODBC Driver for SQL Server)
def get_db_connection():
    DB_CONN_STR = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=LilKoon;"
    "DATABASE=QLNS;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
    )
    return pyodbc.connect(DB_CONN_STR)


# --- Hàm kiểm tra đăng nhập và lấy quyền ---
# Đây là hàm quan trọng nhất
# trong ham.py

# Trong file ham.py
# (Nhớ import thư viện: from werkzeug.security import check_password_hash)

def kiem_tra_dang_nhap(username, password):
    conn = get_db_connection()
    if not conn: return None
    try:
        cursor = conn.cursor()
        query = "SELECT MaNV, TaiKhoan, RoleID FROM Account WHERE TaiKhoan = ? AND MatKhau = ?"
        cursor.execute(query, (username, password))
        row = cursor.fetchone()
        if row:
            return {'ma_nv': row.MaNV, 'tai_khoan': row.TaiKhoan, 'role_id': row.RoleID}
        return None
    finally:
        conn.close()

# --- PROFILE (HỒ SƠ) ---
def lay_thong_tin_nhan_vien(ma_nv):
    conn = get_db_connection()
    if not conn: return None
    try:
        cursor = conn.cursor()
        # Sửa lại: Lấy e.RoleID làm Chức vụ (để hiện 'NhanVien' thay vì số 2)
        query = """
        SELECT e.MaNV, e.HoTen, e.NamSinh, e.DiaChi, e.SoDienThoai, e.email, e.LuongCoBan, e.RoleID as ChucVu
        FROM Employee e
        WHERE e.MaNV = ?
        """
        cursor.execute(query, (ma_nv,))
        row = cursor.fetchone()
        if row:
            return {
                'MaNV': row.MaNV, 'HoTen': row.HoTen, 'NamSinh': row.NamSinh,
                'DiaChi': row.DiaChi, 'SoDienThoai': row.SoDienThoai, 'Email': row.email,
                'LuongCoBan': row.LuongCoBan, 'ChucVu': row.ChucVu
            }
        return None
    finally:
        conn.close()

def cap_nhat_profile(ma_nv, sdt, email, dia_chi):
    conn = get_db_connection()
    if not conn: return False
    try:
        cursor = conn.cursor()
        # Cập nhật thông tin vào bảng Employee
        query = "UPDATE Employee SET SoDienThoai = ?, email = ?, DiaChi = ? WHERE MaNV = ?"
        cursor.execute(query, (sdt, email, dia_chi, ma_nv))
        conn.commit()
        return True
    except Exception as e:
        print(f"Lỗi update profile: {e}")
        return False
    finally:
        conn.close()

# --- TRANG CHỦ & LƯƠNG ---
def lay_trang_thai_cham_cong_hom_nay(ma_nv):
    conn = get_db_connection()
    if not conn: return None
    try:
        cursor = conn.cursor()
        query = """
        SELECT CheckIn, CheckOut 
        FROM AttendLog 
        WHERE MaNV = ? AND CAST(CheckIn AS DATE) = CAST(GETDATE() AS DATE)
        """
        cursor.execute(query, (ma_nv,))
        row = cursor.fetchone()
        if row:
            return {'CheckIn': row.CheckIn, 'CheckOut': row.CheckOut}
        return None
    finally:
        conn.close()
#Bang luong
def lay_bang_luong(ma_nv, thang=None, nam=None):
    """
    Lấy lịch sử lương.
    - Nếu có thang/nam: Lọc theo tháng năm.
    - Nếu không: Lấy toàn bộ.
    """
    conn = get_db_connection()
    if not conn: return []
    try:
        cursor = conn.cursor()
        
        # Câu query cơ bản
        query = "SELECT * FROM Salary WHERE MaNV = ?"
        params = [ma_nv]

        # Nếu người dùng muốn lọc
        if thang and nam:
            query += " AND Thang = ? AND Nam = ?"
            params.append(thang)
            params.append(nam)
            
        # Sắp xếp mới nhất lên đầu
        query += " ORDER BY Nam DESC, Thang DESC"
        
        cursor.execute(query, tuple(params))
        
        # Chuyển đổi thành list dictionary
        columns = [column[0] for column in cursor.description]
        results = []
        for row in cursor.fetchall():
            item = dict(zip(columns, row))
            # Format ngày tạo
            if item.get('NgayTao'):
                item['NgayTao'] = item['NgayTao'].strftime('%d/%m/%Y')
            results.append(item)
            
        return results
    except Exception as e:
        print(f"Lỗi lấy bảng lương: {e}")
        return []
    finally:
        conn.close()

# --- LỊCH SỬ CHẤM CÔNG (CALENDAR) ---
def lay_du_lieu_cham_cong_thang(ma_nv, thang, nam):
    conn = get_db_connection()
    if not conn: return {}
    data_cham_cong = {}
    try:
        cursor = conn.cursor()
        query = """
        SELECT DAY(CheckIn) as Ngay, CheckIn, CheckOut 
        FROM AttendLog 
        WHERE MaNV = ? AND MONTH(CheckIn) = ? AND YEAR(CheckIn) = ?
        """
        cursor.execute(query, (ma_nv, thang, nam))
        rows = cursor.fetchall()
        
        for row in rows:
            gio_vao = row.CheckIn.strftime('%H:%M') if row.CheckIn else "--:--"
            gio_ra = row.CheckOut.strftime('%H:%M') if row.CheckOut else "--:--"
            
            # LOGIC MỚI: Xác định màu sắc
            # - Xanh (success): Đủ CheckIn + CheckOut
            # - Cam (warning): Có CheckIn nhưng thiếu CheckOut
            color_status = 'success'
            if row.CheckIn and not row.CheckOut:
                color_status = 'warning'

            data_cham_cong[row.Ngay] = {
                'check_in': gio_vao,
                'check_out': gio_ra,
                'color': color_status # Trả về màu để HTML hiển thị
            }
        return data_cham_cong
    except Exception as e:
        print(f"Lỗi calendar: {e}")
        return {}
    finally:
        conn.close()
        
def lay_lich_lam_viec(ma_nv, tuan_start, tuan_end):
    """
    Lấy lịch làm việc trong khoảng thời gian (Start -> End).
    Trả về Dict: { 'yyyy-mm-dd': {TenCa, GioBatDau, GioKetThuc} }
    """
    conn = get_db_connection()
    if not conn: return {}
    
    lich_data = {}
    try:
        cursor = conn.cursor()
        # Join bảng PhanCa và CaLamViec
        query = """
        SELECT p.NgayLamViec, c.TenCa, c.GioBatDau, c.GioKetThuc
        FROM PhanCa p
        JOIN CaLamViec c ON p.MaCa = c.MaCa
        WHERE p.MaNV = ? AND p.NgayLamViec BETWEEN ? AND ?
        """
        cursor.execute(query, (ma_nv, tuan_start, tuan_end))
        rows = cursor.fetchall()
        
        for row in rows:
            # Chuyển ngày thành string 'YYYY-MM-DD' để làm key cho dễ tra cứu
            ngay_str = row.NgayLamViec.strftime('%Y-%m-%d')
            
            # Format giờ (bỏ giây thừa)
            gio_bd = row.GioBatDau.strftime('%H:%M') if row.GioBatDau else ""
            gio_kt = row.GioKetThuc.strftime('%H:%M') if row.GioKetThuc else ""
            
            lich_data[ngay_str] = {
                'TenCa': row.TenCa,
                'GioBatDau': gio_bd,
                'GioKetThuc': gio_kt
            }
            
        return lich_data
    except Exception as e:
        print(f"Lỗi lấy lịch: {e}")
        return {}
    finally:
        conn.close()