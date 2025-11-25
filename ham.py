import pyodbc
from werkzeug.security import check_password_hash, generate_password_hash 
from datetime import datetime, timedelta

# --- Cấu hình kết nối MS SQL Server ---
def get_db_connection():
    DB_CONN_STR = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=LilKoon;"
    "DATABASE=QLNS;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
    )
    return pyodbc.connect(DB_CONN_STR)

# sau nay update co the su dung thư viện: from werkzeug.security import check_password_hash)
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
        query = """
        SELECT e.MaNV, e.HoTen, e.NamSinh, e.DiaChi, e.SoDienThoai, e.email, e.LuongCoBan, 
               e.RoleID as ChucVu, e.NgayVaoLam,
               p.TenPhongBan
        FROM Employee e
        LEFT JOIN PhongBan p ON e.PhongBanID = p.PhongBanID
        WHERE e.MaNV = ?
        """
        cursor.execute(query, (ma_nv,))
        row = cursor.fetchone()
        if row:
            ngay_vao = row.NgayVaoLam.strftime('%d/%m/%Y') if row.NgayVaoLam else "Chưa cập nhật"
            phong_ban = row.TenPhongBan if row.TenPhongBan else "Chưa phân phòng"
            
            return {
                'MaNV': row.MaNV, 
                'HoTen': row.HoTen, 
                'NamSinh': row.NamSinh,
                'DiaChi': row.DiaChi, 
                'SoDienThoai': row.SoDienThoai, 
                'Email': row.email,
                'LuongCoBan': row.LuongCoBan, 
                'ChucVu': row.ChucVu,
                'TenPhongBan': phong_ban,
                'NgayVaoLam': ngay_vao 
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
        
        
# --- ADMIN ---
def lay_thong_ke_dashboard():
    """
    Tính toán các con số thống kê cho Dashboard
    """
    conn = get_db_connection()
    if not conn: return {'total': 0, 'present': 0, 'late': 0, 'absent': 0}
    
    stats = {}
    try:
        cursor = conn.cursor()
        
        # 1. Tổng số nhân viên
        cursor.execute("SELECT COUNT(*) FROM Employee")
        stats['total'] = cursor.fetchone()[0]

        # 2. Số người có mặt hôm nay (Đã Check-in)
        cursor.execute("SELECT COUNT(DISTINCT MaNV) FROM AttendLog WHERE CAST(CheckIn AS DATE) = CAST(GETDATE() AS DATE)")
        stats['present'] = cursor.fetchone()[0]

        # 3. Số người đi muộn (Giả sử quy định là sau 08:00:00)
        # Bạn có thể sửa '08:00:00' thành giờ quy định của công ty bạn
        cursor.execute("SELECT COUNT(*) FROM AttendLog WHERE CAST(CheckIn AS DATE) = CAST(GETDATE() AS DATE) AND CAST(CheckIn AS TIME) > '08:00:00'")
        stats['late'] = cursor.fetchone()[0]

        # 4. Số người vắng mặt (Tổng - Có mặt)
        # Lưu ý: Số này chỉ chính xác tương đối vào cuối ngày
        stats['absent'] = stats['total'] - stats['present']
        if stats['absent'] < 0: stats['absent'] = 0

        return stats
    except Exception as e:
        print(f"Lỗi lấy stats: {e}")
        return {'total': 0, 'present': 0, 'late': 0, 'absent': 0}
    finally:
        conn.close()

def lay_hoat_dong_gan_day():
    """
    Lấy 5 hoạt động chấm công mới nhất của tất cả nhân viên
    """
    conn = get_db_connection()
    if not conn: return []
    try:
        cursor = conn.cursor()
        # Join bảng AttendLog với Employee để lấy tên
        query = """
        SELECT TOP 5 a.CheckIn, a.CheckOut, e.HoTen
        FROM AttendLog a
        JOIN Employee e ON a.MaNV = e.MaNV
        -- Lấy hoạt động trong ngày hôm nay
        WHERE CAST(a.CheckIn AS DATE) = CAST(GETDATE() AS DATE)
        ORDER BY a.CheckIn DESC
        """
        cursor.execute(query)
        
        columns = [column[0] for column in cursor.description]
        results = []
        for row in cursor.fetchall():
            item = dict(zip(columns, row))
            
            # Xử lý logic để hiển thị: Ai vừa Check-in hoặc ai vừa Check-out
            # (Logic đơn giản: Nếu có CheckOut thì hiển thị giờ ra, ngược lại hiển thị giờ vào)
            if item['CheckOut']:
                item['Time'] = item['CheckOut'].strftime('%H:%M:%S')
                item['Type'] = 'Check-out'
                item['Status'] = 'Hoàn thành'
                item['Color'] = 'primary'
            else:
                item['Time'] = item['CheckIn'].strftime('%H:%M:%S')
                item['Type'] = 'Check-in'
                
                # Kiểm tra đi muộn cho từng dòng
                checkin_time = item['CheckIn'].time()
                limit_time = datetime.strptime('08:00:00', '%H:%M:%S').time()
                
                if checkin_time > limit_time:
                    item['Status'] = 'Đi muộn'
                    item['Color'] = 'warning text-dark'
                else:
                    item['Status'] = 'Đúng giờ'
                    item['Color'] = 'success'
            
            results.append(item)
        return results
    except Exception as e:
        print(f"Lỗi lấy activity: {e}")
        return []
    finally:
        conn.close()
        

# --- QUẢN LÝ NHÂN SỰ (ADMIN) ---

def lay_danh_sach_nhan_vien(tu_khoa='', cac_truong=None):
    """
    Lấy danh sách nhân viên có hỗ trợ tìm kiếm theo nhiều tiêu chí.
    - tu_khoa: Chuỗi tìm kiếm.
    - cac_truong: List các trường cần tìm ['ma_nv', 'ho_ten', 'chuc_vu', 'phong_ban'].
    """
    conn = get_db_connection()
    if not conn: return []
    try:
        cursor = conn.cursor()
        
        # Query cơ bản
        query = """
        SELECT e.MaNV, e.HoTen, e.NamSinh, e.SoDienThoai, e.email, e.LuongCoBan, 
               e.RoleID as ChucVu, e.NgayVaoLam, p.TenPhongBan,
               a.TaiKhoan, a.MatKhau
        FROM Employee e
        LEFT JOIN PhongBan p ON e.PhongBanID = p.PhongBanID
        LEFT JOIN Account a ON e.MaNV = a.MaNV
        WHERE 1=1 
        """
        
        params = []
        
        if tu_khoa:
            search_term = f"%{tu_khoa}%"
            conditions = []
            
            # Map giá trị từ checkbox HTML sang tên cột Database
            field_mapping = {
                'ma_nv': 'CAST(e.MaNV AS NVARCHAR(50))', # Chuyển số sang chuỗi để tìm LIKE
                'ho_ten': 'e.HoTen',
                'chuc_vu': 'e.RoleID',
                'phong_ban': 'p.TenPhongBan'
            }
            
            # Nếu người dùng có chọn checkbox
            if cac_truong:
                for field in cac_truong:
                    if field in field_mapping:
                        conditions.append(f"{field_mapping[field]} LIKE ?")
                        params.append(search_term)
            
            # Nếu không chọn checkbox nào nhưng vẫn nhập từ khóa -> Tìm tất cả
            else:
                for col in field_mapping.values():
                    conditions.append(f"{col} LIKE ?")
                    params.append(search_term)
            
            if conditions:
                query += " AND (" + " OR ".join(conditions) + ")"

        query += " ORDER BY e.MaNV DESC"
        
        cursor.execute(query, tuple(params))
        
        # ... (Phần xử lý kết quả giữ nguyên) ...
        columns = [column[0] for column in cursor.description]
        results = []
        for row in cursor.fetchall():
            item = dict(zip(columns, row))
            if item.get('LuongCoBan'): item['LuongCoBan'] = "{:,.0f}".format(item['LuongCoBan'])
            if item.get('NgayVaoLam'): item['NgayVaoLam'] = item['NgayVaoLam'].strftime('%d/%m/%Y')
            if not item.get('TaiKhoan'): item['TaiKhoan'] = ''; item['MatKhau'] = ''
            results.append(item)
        return results
    except Exception as e:
        print(f"Lỗi tìm kiếm nhân viên: {e}")
        return []
    finally:
        conn.close()

def them_nhan_vien_moi(ho_ten, sdt, email, chuc_vu, luong, phong_ban_id, tai_khoan, mat_khau):
    """Thêm nhân viên và tài khoản tùy chỉnh"""
    conn = get_db_connection()
    if not conn: return False
    try:
        cursor = conn.cursor()
        
        # 1. Thêm Employee
        query_emp = """
        INSERT INTO Employee (HoTen, SoDienThoai, email, RoleID, LuongCoBan, PhongBanID, NgayVaoLam)
        OUTPUT INSERTED.MaNV
        VALUES (?, ?, ?, ?, ?, ?, GETDATE())
        """
        cursor.execute(query_emp, (ho_ten, sdt, email, chuc_vu, luong, phong_ban_id))
        ma_nv_moi = cursor.fetchone()[0]
        
        # 2. Thêm Account với thông tin nhập vào
        query_acc = """
        INSERT INTO Account (MaNV, TaiKhoan, MatKhau, RoleID)
        VALUES (?, ?, ?, ?)
        """
        cursor.execute(query_acc, (ma_nv_moi, tai_khoan, mat_khau, chuc_vu))
        
        conn.commit()
        return True
    except Exception as e:
        print(f"Lỗi thêm nhân viên: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def cap_nhat_nhan_vien_admin(ma_nv, ho_ten, sdt, email, chuc_vu, luong, phong_ban_id, tai_khoan, mat_khau):
    """Cập nhật thông tin nhân viên VÀ tài khoản"""
    conn = get_db_connection()
    if not conn: return False
    try:
        cursor = conn.cursor()
        
        # 1. Cập nhật Employee
        query_emp = """
        UPDATE Employee 
        SET HoTen = ?, SoDienThoai = ?, email = ?, RoleID = ?, LuongCoBan = ?, PhongBanID = ?
        WHERE MaNV = ?
        """
        cursor.execute(query_emp, (ho_ten, sdt, email, chuc_vu, luong, phong_ban_id, ma_nv))
        
        # 2. Cập nhật Account (Tài khoản, Mật khẩu, Quyền)
        # Kiểm tra xem nhân viên này đã có dòng trong bảng Account chưa
        cursor.execute("SELECT COUNT(*) FROM Account WHERE MaNV = ?", (ma_nv,))
        exists = cursor.fetchone()[0]
        
        if exists:
            query_acc = "UPDATE Account SET TaiKhoan = ?, MatKhau = ?, RoleID = ? WHERE MaNV = ?"
            cursor.execute(query_acc, (tai_khoan, mat_khau, chuc_vu, ma_nv))
        else:
            # Nếu chưa có account thì tạo mới (trường hợp dữ liệu cũ bị thiếu)
            query_acc = "INSERT INTO Account (MaNV, TaiKhoan, MatKhau, RoleID) VALUES (?, ?, ?, ?)"
            cursor.execute(query_acc, (ma_nv, tai_khoan, mat_khau, chuc_vu))
        
        conn.commit()
        return True
    except Exception as e:
        print(f"Lỗi sửa nhân viên: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def xoa_nhan_vien(ma_nv):
    """Xóa nhân viên"""
    conn = get_db_connection()
    if not conn: return False
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM Account WHERE MaNV = ?", (ma_nv,))
        cursor.execute("DELETE FROM Salary WHERE MaNV = ?", (ma_nv,))
        cursor.execute("DELETE FROM AttendLog WHERE MaNV = ?", (ma_nv,))
        cursor.execute("DELETE FROM PhanCa WHERE MaNV = ?", (ma_nv,))
        cursor.execute("DELETE FROM FaceData WHERE MaNV = ?", (ma_nv,))
        cursor.execute("DELETE FROM Employee WHERE MaNV = ?", (ma_nv,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Lỗi xóa nhân viên: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def lay_danh_sach_phong_ban():
    conn = get_db_connection()
    if not conn: return []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT PhongBanID, TenPhongBan FROM PhongBan")
        return [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
    finally:
        conn.close()
        
        
#QLChamCong
def lay_bang_cham_cong_ngay(ngay_xem):
    """
    Lấy dữ liệu chấm công kết hợp với Ca làm việc để tính trạng thái chính xác.
    """
    conn = get_db_connection()
    if not conn: return []
    try:
        cursor = conn.cursor()
        
        # Query phức tạp hơn: Join thêm PhanCa và CaLamViec để lấy giờ quy định
        query = """
        SELECT a.LogId, e.MaNV, e.HoTen, p.TenPhongBan, 
               a.CheckIn, a.CheckOut,
               c.TenCa, c.GioBatDau, c.GioKetThuc
        FROM AttendLog a
        JOIN Employee e ON a.MaNV = e.MaNV
        LEFT JOIN PhongBan p ON e.PhongBanID = p.PhongBanID
        -- Join để lấy ca làm việc của nhân viên trong ngày đó
        LEFT JOIN PhanCa pc ON e.MaNV = pc.MaNV AND pc.NgayLamViec = CAST(a.CheckIn AS DATE)
        LEFT JOIN CaLamViec c ON pc.MaCa = c.MaCa
        WHERE CAST(a.CheckIn AS DATE) = ?
        ORDER BY a.CheckIn DESC
        """
        cursor.execute(query, (ngay_xem,))
        
        columns = [column[0] for column in cursor.description]
        results = []
        for row in cursor.fetchall():
            item = dict(zip(columns, row))
            
            # 1. Xử lý hiển thị giờ
            item['GioVao'] = item['CheckIn'].strftime('%H:%M:%S') if item['CheckIn'] else ""
            item['GioRa'] = item['CheckOut'].strftime('%H:%M:%S') if item['CheckOut'] else ""
            
            # 2. Logic Trạng Thái Phức Tạp
            trang_thai = []
            color = 'success' # Mặc định là xanh (Oke)
            
            # Lấy giờ quy định của ca (Nếu không có phân ca thì mặc định hành chính 8h-17h để so sánh tạm)
            # Lưu ý: GioBatDau trong DB là time, cần convert sang datetime để so sánh
            if item['GioBatDau'] and item['GioKetThuc']:
                # Tạo datetime đầy đủ cho giờ quy định để so sánh
                base_date = item['CheckIn'].date() # Lấy ngày chấm công làm gốc
                
                # Giờ bắt đầu ca
                start_time = datetime.combine(base_date, item['GioBatDau'])
                # Giờ kết thúc ca
                end_time = datetime.combine(base_date, item['GioKetThuc'])
                
                # --- ĐIỀU KIỆN 1: ĐI MUỘN (Cho phép trễ 15p) ---
                limit_late = start_time + timedelta(minutes=15)
                is_late = False
                if item['CheckIn'] > limit_late:
                    is_late = True
                    
                # --- ĐIỀU KIỆN 2: VỀ SỚM ---
                is_early = False
                if item['CheckOut']:
                    if item['CheckOut'] < end_time:
                        is_early = True
                else:
                    # Nếu chưa có CheckOut -> Chưa chấm công về
                    trang_thai.append("Chưa chấm công về")
                    color = 'secondary' # Màu xám
                
                # --- TỔNG HỢP TRẠNG THÁI ---
                if is_late and is_early:
                    trang_thai = ["Đi muộn", "Về sớm"] # Ghi đè nếu bị cả 2 (hoặc append tùy ý)
                    color = 'danger' # Đỏ
                elif is_late:
                    trang_thai.insert(0, "Đi muộn")
                    if color != 'secondary': color = 'warning text-dark' # Vàng
                elif is_early:
                    trang_thai.insert(0, "Về sớm")
                    if color != 'secondary': color = 'warning text-dark'
                
                # Nếu không dính lỗi nào và đã checkout
                if not is_late and not is_early and item['CheckOut']:
                    trang_thai = ["Oke"]
                    
            else:
                # Trường hợp nhân viên đi làm nhưng hôm đó KHÔNG ĐƯỢC PHÂN CA trong bảng PhanCa
                trang_thai = ["Làm không lịch"]
                color = 'info text-dark'

            # Chuyển list trạng thái thành chuỗi: "Đi muộn, Về sớm"
            item['TrangThai'] = ", ".join(trang_thai)
            item['Color'] = color
            
            # Bổ sung tên ca để hiển thị cho rõ (VD: Ca Sáng)
            item['TenCa'] = item['TenCa'] if item['TenCa'] else "Không xác định"

            results.append(item)
            
        return results
    except Exception as e:
        print(f"Lỗi lấy chấm công logic mới: {e}")
        return []
    finally:
        conn.close()

def admin_sua_cham_cong(log_id, gio_vao, gio_ra, ngay_chon):
    """
    Admin sửa giờ chấm công thủ công (Fix lỗi quên check-in/out)
    """
    conn = get_db_connection()
    if not conn: return False
    try:
        cursor = conn.cursor()
        
        # Tạo chuỗi datetime đầy đủ: '2023-11-25 08:00:00'
        dt_vao = f"{ngay_chon} {gio_vao}" if gio_vao else None
        dt_ra = f"{ngay_chon} {gio_ra}" if gio_ra else None
        
        query = """
        UPDATE AttendLog 
        SET CheckIn = ?, CheckOut = ?
        WHERE LogId = ?
        """
        cursor.execute(query, (dt_vao, dt_ra, log_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"Lỗi sửa chấm công: {e}")
        return False
    finally:
        conn.close()